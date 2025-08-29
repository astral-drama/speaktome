"""
Dependency Injection Container Module

Provides dependency injection capabilities with functional composition.
"""

from .dependency_container import (
    DependencyContainer,
    ServiceScope,
    ServiceRegistration,
    LifetimeScope,
    get_container,
    create_scope
)

__all__ = [
    "DependencyContainer",
    "ServiceScope",
    "ServiceRegistration", 
    "LifetimeScope",
    "get_container",
    "create_scope"
]