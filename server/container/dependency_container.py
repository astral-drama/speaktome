#!/usr/bin/env python3

"""
Dependency Injection Container

Provides a functional approach to dependency injection using Result monads.
Supports singleton, transient, and factory registrations with lazy loading.
"""

import logging
import asyncio
import inspect
from typing import Dict, Any, Optional, Callable, TypeVar, Generic, Type, Union, get_type_hints
from enum import Enum
from dataclasses import dataclass, field

from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

T = TypeVar('T')

class LifetimeScope(Enum):
    """Dependency lifetime management"""
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"

@dataclass
class ServiceRegistration:
    """Service registration information"""
    name: str
    service_type: Type
    implementation: Optional[Type] = None
    factory: Optional[Callable] = None
    instance: Any = None
    lifetime: LifetimeScope = LifetimeScope.TRANSIENT
    dependencies: Dict[str, str] = field(default_factory=dict)
    initialized: bool = False
    lazy: bool = True

class DependencyContainer:
    """Dependency injection container with functional composition"""
    
    def __init__(self):
        self._services: Dict[str, ServiceRegistration] = {}
        self._instances: Dict[str, Any] = {}
        self._resolving: set = set()  # Circular dependency detection
        self._disposed = False
    
    def register_singleton(self, 
                          service_type: Type[T], 
                          implementation: Optional[Type[T]] = None,
                          factory: Optional[Callable[[], T]] = None,
                          name: Optional[str] = None) -> Result['DependencyContainer', str]:
        """Register a singleton service"""
        return self._register_service(
            service_type=service_type,
            implementation=implementation,
            factory=factory,
            lifetime=LifetimeScope.SINGLETON,
            name=name
        )
    
    def register_transient(self, 
                          service_type: Type[T], 
                          implementation: Optional[Type[T]] = None,
                          factory: Optional[Callable[[], T]] = None,
                          name: Optional[str] = None) -> Result['DependencyContainer', str]:
        """Register a transient service"""
        return self._register_service(
            service_type=service_type,
            implementation=implementation,
            factory=factory,
            lifetime=LifetimeScope.TRANSIENT,
            name=name
        )
    
    def register_scoped(self, 
                       service_type: Type[T], 
                       implementation: Optional[Type[T]] = None,
                       factory: Optional[Callable[[], T]] = None,
                       name: Optional[str] = None) -> Result['DependencyContainer', str]:
        """Register a scoped service"""
        return self._register_service(
            service_type=service_type,
            implementation=implementation,
            factory=factory,
            lifetime=LifetimeScope.SCOPED,
            name=name
        )
    
    def register_instance(self, 
                         service_type: Type[T], 
                         instance: T,
                         name: Optional[str] = None) -> Result['DependencyContainer', str]:
        """Register an existing instance as singleton"""
        try:
            service_name = name or self._get_service_name(service_type)
            
            registration = ServiceRegistration(
                name=service_name,
                service_type=service_type,
                instance=instance,
                lifetime=LifetimeScope.SINGLETON,
                initialized=True,
                lazy=False
            )
            
            self._services[service_name] = registration
            self._instances[service_name] = instance
            
            logger.debug(f"Registered instance: {service_name}")
            return Success(self)
            
        except Exception as e:
            logger.error(f"Failed to register instance: {e}")
            return Failure(f"Instance registration failed: {str(e)}")
    
    def resolve(self, service_type: Type[T], name: Optional[str] = None) -> Result[T, str]:
        """Resolve a service by type"""
        if self._disposed:
            return Failure("Container has been disposed")
        
        service_name = name or self._get_service_name(service_type)
        return self._resolve_service(service_name)
    
    def resolve_by_name(self, name: str) -> Result[Any, str]:
        """Resolve a service by name"""
        if self._disposed:
            return Failure("Container has been disposed")
        
        return self._resolve_service(name)
    
    async def resolve_async(self, service_type: Type[T], name: Optional[str] = None) -> Result[T, str]:
        """Resolve a service asynchronously"""
        result = self.resolve(service_type, name)
        
        if result.is_failure():
            return result
        
        service = result.get_value()
        
        # If service has async initialization, call it
        if hasattr(service, 'initialize') and asyncio.iscoroutinefunction(service.initialize):
            try:
                await service.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize service asynchronously: {e}")
                return Failure(f"Async initialization failed: {str(e)}")
        
        return Success(service)
    
    def is_registered(self, service_type: Type, name: Optional[str] = None) -> bool:
        """Check if a service is registered"""
        service_name = name or self._get_service_name(service_type)
        return service_name in self._services
    
    def get_registered_services(self) -> Dict[str, ServiceRegistration]:
        """Get all registered services"""
        return self._services.copy()
    
    async def initialize_all_singletons(self) -> Result[Dict[str, bool], str]:
        """Initialize all singleton services"""
        try:
            results = {}
            
            for service_name, registration in self._services.items():
                if registration.lifetime == LifetimeScope.SINGLETON and registration.lazy:
                    try:
                        resolve_result = await self.resolve_async(registration.service_type, service_name)
                        results[service_name] = resolve_result.is_success()
                        
                        if resolve_result.is_failure():
                            logger.error(f"Failed to initialize singleton {service_name}: {resolve_result.get_error()}")
                        else:
                            logger.info(f"Initialized singleton: {service_name}")
                            
                    except Exception as e:
                        logger.error(f"Exception initializing singleton {service_name}: {e}")
                        results[service_name] = False
            
            return Success(results)
            
        except Exception as e:
            logger.error(f"Failed to initialize singletons: {e}")
            return Failure(f"Singleton initialization failed: {str(e)}")
    
    async def dispose(self) -> Result[None, str]:
        """Dispose the container and all managed instances"""
        if self._disposed:
            return Success(None)
        
        try:
            # Dispose instances that support it
            for service_name, instance in self._instances.items():
                try:
                    if hasattr(instance, 'dispose'):
                        if asyncio.iscoroutinefunction(instance.dispose):
                            await instance.dispose()
                        else:
                            instance.dispose()
                    elif hasattr(instance, 'cleanup'):
                        if asyncio.iscoroutinefunction(instance.cleanup):
                            await instance.cleanup()
                        else:
                            instance.cleanup()
                except Exception as e:
                    logger.error(f"Error disposing service {service_name}: {e}")
            
            # Clear all data
            self._services.clear()
            self._instances.clear()
            self._resolving.clear()
            self._disposed = True
            
            logger.info("Dependency container disposed")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error disposing container: {e}")
            return Failure(f"Container disposal failed: {str(e)}")
    
    def _register_service(self,
                         service_type: Type[T],
                         implementation: Optional[Type[T]] = None,
                         factory: Optional[Callable] = None,
                         lifetime: LifetimeScope = LifetimeScope.TRANSIENT,
                         name: Optional[str] = None) -> Result['DependencyContainer', str]:
        """Internal service registration"""
        try:
            if implementation is None and factory is None:
                implementation = service_type
            
            if implementation and factory:
                return Failure("Cannot specify both implementation and factory")
            
            service_name = name or self._get_service_name(service_type)
            
            # Analyze dependencies
            dependencies = {}
            if implementation:
                dependencies = self._analyze_dependencies(implementation)
            
            registration = ServiceRegistration(
                name=service_name,
                service_type=service_type,
                implementation=implementation,
                factory=factory,
                lifetime=lifetime,
                dependencies=dependencies
            )
            
            self._services[service_name] = registration
            
            logger.debug(f"Registered service: {service_name} ({lifetime.value})")
            return Success(self)
            
        except Exception as e:
            logger.error(f"Failed to register service: {e}")
            return Failure(f"Service registration failed: {str(e)}")
    
    def _resolve_service(self, service_name: str) -> Result[Any, str]:
        """Internal service resolution"""
        try:
            # Check for circular dependencies
            if service_name in self._resolving:
                return Failure(f"Circular dependency detected for service: {service_name}")
            
            # Check if service is registered
            if service_name not in self._services:
                return Failure(f"Service not registered: {service_name}")
            
            registration = self._services[service_name]
            
            # Return existing instance for singletons
            if (registration.lifetime == LifetimeScope.SINGLETON and 
                service_name in self._instances):
                return Success(self._instances[service_name])
            
            # Mark as resolving
            self._resolving.add(service_name)
            
            try:
                # Create instance
                instance_result = self._create_instance(registration)
                if instance_result.is_failure():
                    return instance_result
                
                instance = instance_result.get_value()
                
                # Store singleton instances
                if registration.lifetime == LifetimeScope.SINGLETON:
                    self._instances[service_name] = instance
                
                return Success(instance)
                
            finally:
                self._resolving.discard(service_name)
                
        except Exception as e:
            logger.error(f"Failed to resolve service {service_name}: {e}")
            return Failure(f"Service resolution failed: {str(e)}")
    
    def _create_instance(self, registration: ServiceRegistration) -> Result[Any, str]:
        """Create a service instance"""
        try:
            # Use existing instance if available
            if registration.instance is not None:
                return Success(registration.instance)
            
            # Use factory if provided
            if registration.factory:
                try:
                    instance = registration.factory()
                    return Success(instance)
                except Exception as e:
                    return Failure(f"Factory failed: {str(e)}")
            
            # Create from implementation
            if registration.implementation:
                return self._create_from_implementation(registration)
            
            return Failure(f"No way to create instance for {registration.name}")
            
        except Exception as e:
            logger.error(f"Failed to create instance: {e}")
            return Failure(f"Instance creation failed: {str(e)}")
    
    def _create_from_implementation(self, registration: ServiceRegistration) -> Result[Any, str]:
        """Create instance from implementation class"""
        try:
            implementation = registration.implementation
            
            # Resolve constructor dependencies
            constructor_args = {}
            
            for param_name, service_name in registration.dependencies.items():
                dependency_result = self._resolve_service(service_name)
                if dependency_result.is_failure():
                    return Failure(f"Failed to resolve dependency {service_name}: {dependency_result.get_error()}")
                
                constructor_args[param_name] = dependency_result.get_value()
            
            # Create instance
            instance = implementation(**constructor_args)
            return Success(instance)
            
        except Exception as e:
            logger.error(f"Failed to create from implementation: {e}")
            return Failure(f"Implementation instantiation failed: {str(e)}")
    
    def _analyze_dependencies(self, implementation: Type) -> Dict[str, str]:
        """Analyze constructor dependencies using type hints"""
        try:
            dependencies = {}
            
            # Get constructor signature
            init_method = implementation.__init__
            signature = inspect.signature(init_method)
            
            # Get type hints
            try:
                type_hints = get_type_hints(init_method)
            except:
                type_hints = {}
            
            # Analyze parameters (skip 'self')
            for param_name, param in signature.parameters.items():
                if param_name == 'self':
                    continue
                
                # Use type hint if available
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    service_name = self._get_service_name(param_type)
                    dependencies[param_name] = service_name
                elif param.annotation != inspect.Parameter.empty:
                    service_name = self._get_service_name(param.annotation)
                    dependencies[param_name] = service_name
            
            return dependencies
            
        except Exception as e:
            logger.warning(f"Failed to analyze dependencies for {implementation}: {e}")
            return {}
    
    def _get_service_name(self, service_type: Type) -> str:
        """Get service name from type"""
        # Handle generic types
        if hasattr(service_type, '__origin__'):
            return str(service_type)
        
        # Use fully qualified name
        module = getattr(service_type, '__module__', '')
        name = getattr(service_type, '__name__', str(service_type))
        
        if module and module != '__main__':
            return f"{module}.{name}"
        else:
            return name

class ServiceScope:
    """Manages scoped services within a specific context"""
    
    def __init__(self, container: DependencyContainer):
        self._container = container
        self._scoped_instances: Dict[str, Any] = {}
        self._disposed = False
    
    def resolve(self, service_type: Type[T], name: Optional[str] = None) -> Result[T, str]:
        """Resolve service within this scope"""
        if self._disposed:
            return Failure("Scope has been disposed")
        
        service_name = name or self._container._get_service_name(service_type)
        
        # Check if we have a scoped instance
        if service_name in self._scoped_instances:
            return Success(self._scoped_instances[service_name])
        
        # Resolve from container
        result = self._container.resolve(service_type, name)
        if result.is_failure():
            return result
        
        instance = result.get_value()
        
        # Store scoped instance if it's registered as scoped
        if (service_name in self._container._services and 
            self._container._services[service_name].lifetime == LifetimeScope.SCOPED):
            self._scoped_instances[service_name] = instance
        
        return Success(instance)
    
    async def dispose(self) -> Result[None, str]:
        """Dispose all scoped instances"""
        if self._disposed:
            return Success(None)
        
        try:
            for service_name, instance in self._scoped_instances.items():
                try:
                    if hasattr(instance, 'dispose'):
                        if asyncio.iscoroutinefunction(instance.dispose):
                            await instance.dispose()
                        else:
                            instance.dispose()
                except Exception as e:
                    logger.error(f"Error disposing scoped service {service_name}: {e}")
            
            self._scoped_instances.clear()
            self._disposed = True
            
            return Success(None)
            
        except Exception as e:
            return Failure(f"Scope disposal failed: {str(e)}")

# Global container instance
_global_container = DependencyContainer()

def get_container() -> DependencyContainer:
    """Get the global dependency container"""
    return _global_container

def create_scope(container: Optional[DependencyContainer] = None) -> ServiceScope:
    """Create a new service scope"""
    return ServiceScope(container or _global_container)