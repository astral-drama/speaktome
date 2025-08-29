#!/usr/bin/env python3

"""
Server Status Provider

Centralized status management for the SpeakToMe server.
Provides system information, health metrics, and operational status.
"""

import asyncio
import logging
import time
import psutil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel

from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    """Service status enumeration"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class GPUInfo:
    """GPU information"""
    available: bool = False
    name: Optional[str] = None
    memory_total: Optional[int] = None
    memory_used: Optional[int] = None
    memory_free: Optional[int] = None
    utilization: Optional[float] = None
    temperature: Optional[float] = None

@dataclass
class SystemMetrics:
    """System performance metrics"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used: int = 0
    memory_total: int = 0
    disk_usage_percent: float = 0.0
    network_io: Dict[str, int] = field(default_factory=dict)
    process_count: int = 0

@dataclass
class ServiceMetrics:
    """Service-specific metrics"""
    uptime: float = 0.0
    requests_total: int = 0
    requests_active: int = 0
    requests_failed: int = 0
    active_connections: int = 0
    queue_size: int = 0
    average_processing_time: float = 0.0

class ServerStatus(BaseModel):
    """Complete server status model"""
    status: str
    health: str
    uptime: float
    timestamp: float
    
    # GPU information
    gpu_available: bool
    gpu_name: Optional[str] = None
    gpu_info: Optional[Dict[str, Any]] = None
    
    # Service information
    loaded_models: List[str]
    queue_status: Dict[str, Any]
    active_connections: int
    
    # System metrics
    system_metrics: Optional[Dict[str, Any]] = None
    service_metrics: Optional[Dict[str, Any]] = None

class ServerStatusProvider:
    """Provides comprehensive server status and health information"""
    
    def __init__(self):
        self._start_time = time.time()
        self._service_status = ServiceStatus.STARTING
        self._health_status = HealthStatus.HEALTHY
        
        # Metrics tracking
        self._request_counters = {
            "total": 0,
            "active": 0,
            "failed": 0
        }
        
        self._processing_times: List[float] = []
        self._max_processing_history = 100
        
        # Health check functions
        self._health_checks: Dict[str, callable] = {}
        
        # External status providers
        self._external_providers: Dict[str, callable] = {}
        
        logger.info("ServerStatusProvider initialized")
    
    def set_service_status(self, status: ServiceStatus) -> None:
        """Set the current service status"""
        if self._service_status != status:
            logger.info(f"Service status changed: {self._service_status.value} -> {status.value}")
            self._service_status = status
    
    def set_health_status(self, health: HealthStatus) -> None:
        """Set the current health status"""
        if self._health_status != health:
            logger.warning(f"Health status changed: {self._health_status.value} -> {health.value}")
            self._health_status = health
    
    def increment_request_counter(self, counter_type: str) -> None:
        """Increment a request counter"""
        if counter_type in self._request_counters:
            self._request_counters[counter_type] += 1
    
    def record_processing_time(self, processing_time: float) -> None:
        """Record a processing time for metrics"""
        self._processing_times.append(processing_time)
        
        # Keep only recent processing times
        if len(self._processing_times) > self._max_processing_history:
            self._processing_times = self._processing_times[-self._max_processing_history:]
    
    def add_health_check(self, name: str, check_func: callable) -> None:
        """Add a health check function"""
        self._health_checks[name] = check_func
        logger.debug(f"Added health check: {name}")
    
    def add_external_status_provider(self, name: str, provider_func: callable) -> None:
        """Add an external status provider (e.g., transcription service)"""
        self._external_providers[name] = provider_func
        logger.debug(f"Added external status provider: {name}")
    
    async def get_status(self, include_system_metrics: bool = True) -> Result[ServerStatus, str]:
        """Get comprehensive server status"""
        try:
            current_time = time.time()
            uptime = current_time - self._start_time
            
            # Get GPU information
            gpu_info_result = self._get_gpu_info()
            gpu_info = gpu_info_result.get_value() if gpu_info_result.is_success() else GPUInfo()
            
            # Get external status information
            external_status = await self._get_external_status()
            
            # Build base status
            status = ServerStatus(
                status=self._service_status.value,
                health=self._health_status.value,
                uptime=uptime,
                timestamp=current_time,
                gpu_available=gpu_info.available,
                gpu_name=gpu_info.name,
                gpu_info=self._gpu_info_to_dict(gpu_info) if gpu_info.available else None,
                loaded_models=external_status.get("loaded_models", []),
                queue_status=external_status.get("queue_status", {}),
                active_connections=external_status.get("active_connections", 0)
            )
            
            # Add system metrics if requested
            if include_system_metrics:
                system_metrics_result = self._get_system_metrics()
                if system_metrics_result.is_success():
                    status.system_metrics = self._system_metrics_to_dict(system_metrics_result.get_value())
                
                service_metrics = self._get_service_metrics()
                status.service_metrics = self._service_metrics_to_dict(service_metrics)
            
            return Success(status)
            
        except Exception as e:
            logger.error(f"Failed to get server status: {e}")
            return Failure(f"Status collection failed: {str(e)}")
    
    async def get_health_check(self) -> Result[Dict[str, Any], str]:
        """Perform health checks and return results"""
        try:
            health_results = {}
            overall_healthy = True
            
            # Run all registered health checks
            for name, check_func in self._health_checks.items():
                try:
                    result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                    health_results[name] = {
                        "status": "healthy" if result else "unhealthy",
                        "checked_at": time.time()
                    }
                    if not result:
                        overall_healthy = False
                except Exception as e:
                    health_results[name] = {
                        "status": "error",
                        "error": str(e),
                        "checked_at": time.time()
                    }
                    overall_healthy = False
            
            # Update health status based on checks
            if overall_healthy:
                self.set_health_status(HealthStatus.HEALTHY)
            else:
                self.set_health_status(HealthStatus.UNHEALTHY)
            
            return Success({
                "overall_status": self._health_status.value,
                "checks": health_results,
                "timestamp": time.time()
            })
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.set_health_status(HealthStatus.UNHEALTHY)
            return Failure(f"Health check failed: {str(e)}")
    
    def get_uptime(self) -> float:
        """Get server uptime in seconds"""
        return time.time() - self._start_time
    
    def _get_gpu_info(self) -> Result[GPUInfo, str]:
        """Get GPU information"""
        try:
            import torch
            
            if not torch.cuda.is_available():
                return Success(GPUInfo(available=False))
            
            gpu_info = GPUInfo(
                available=True,
                name=torch.cuda.get_device_name(0)
            )
            
            # Get memory information
            try:
                memory_info = torch.cuda.mem_get_info(0)
                gpu_info.memory_free = memory_info[0]
                gpu_info.memory_total = memory_info[1]
                gpu_info.memory_used = gpu_info.memory_total - gpu_info.memory_free
            except:
                pass
            
            # Get utilization (if nvidia-ml-py is available)
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_info.utilization = util.gpu
                
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                gpu_info.temperature = temp
                
            except ImportError:
                pass  # nvidia-ml-py not available
            except Exception:
                pass  # Other NVML errors
            
            return Success(gpu_info)
            
        except ImportError:
            # PyTorch not available
            return Success(GPUInfo(available=False))
        except Exception as e:
            logger.error(f"GPU info collection failed: {e}")
            return Failure(f"GPU info failed: {str(e)}")
    
    def _get_system_metrics(self) -> Result[SystemMetrics, str]:
        """Get system performance metrics"""
        try:
            metrics = SystemMetrics(
                cpu_percent=psutil.cpu_percent(interval=None),
                memory_percent=psutil.virtual_memory().percent,
                memory_used=psutil.virtual_memory().used,
                memory_total=psutil.virtual_memory().total,
                disk_usage_percent=psutil.disk_usage('/').percent,
                process_count=len(psutil.pids())
            )
            
            # Network I/O
            try:
                net_io = psutil.net_io_counters()
                metrics.network_io = {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv
                }
            except:
                pass
            
            return Success(metrics)
            
        except Exception as e:
            logger.error(f"System metrics collection failed: {e}")
            return Failure(f"System metrics failed: {str(e)}")
    
    def _get_service_metrics(self) -> ServiceMetrics:
        """Get service-specific metrics"""
        avg_processing_time = 0.0
        if self._processing_times:
            avg_processing_time = sum(self._processing_times) / len(self._processing_times)
        
        return ServiceMetrics(
            uptime=self.get_uptime(),
            requests_total=self._request_counters["total"],
            requests_active=self._request_counters["active"],
            requests_failed=self._request_counters["failed"],
            average_processing_time=avg_processing_time
        )
    
    async def _get_external_status(self) -> Dict[str, Any]:
        """Get status from external providers"""
        external_status = {}
        
        for name, provider_func in self._external_providers.items():
            try:
                if asyncio.iscoroutinefunction(provider_func):
                    result = await provider_func()
                else:
                    result = provider_func()
                
                if isinstance(result, dict):
                    external_status.update(result)
                else:
                    external_status[name] = result
                    
            except Exception as e:
                logger.error(f"External status provider '{name}' failed: {e}")
                external_status[f"{name}_error"] = str(e)
        
        return external_status
    
    def _gpu_info_to_dict(self, gpu_info: GPUInfo) -> Dict[str, Any]:
        """Convert GPUInfo to dictionary"""
        return {
            "name": gpu_info.name,
            "memory_total": gpu_info.memory_total,
            "memory_used": gpu_info.memory_used,
            "memory_free": gpu_info.memory_free,
            "utilization": gpu_info.utilization,
            "temperature": gpu_info.temperature
        }
    
    def _system_metrics_to_dict(self, metrics: SystemMetrics) -> Dict[str, Any]:
        """Convert SystemMetrics to dictionary"""
        return {
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "memory_used": metrics.memory_used,
            "memory_total": metrics.memory_total,
            "disk_usage_percent": metrics.disk_usage_percent,
            "network_io": metrics.network_io,
            "process_count": metrics.process_count
        }
    
    def _service_metrics_to_dict(self, metrics: ServiceMetrics) -> Dict[str, Any]:
        """Convert ServiceMetrics to dictionary"""
        return {
            "uptime": metrics.uptime,
            "requests_total": metrics.requests_total,
            "requests_active": metrics.requests_active,
            "requests_failed": metrics.requests_failed,
            "active_connections": metrics.active_connections,
            "queue_size": metrics.queue_size,
            "average_processing_time": metrics.average_processing_time
        }

# Global instance
server_status_provider = ServerStatusProvider()

def get_server_status_provider() -> ServerStatusProvider:
    """Get the global server status provider instance"""
    return server_status_provider