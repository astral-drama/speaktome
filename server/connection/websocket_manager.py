#!/usr/bin/env python3

"""
WebSocket Connection Manager

Handles WebSocket connections, client lifecycle, and message routing.
Provides a clean separation of concerns for WebSocket connection management.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Set, Optional, Any, Callable, Awaitable
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..functional.result_monad import Result, Success, Failure

logger = logging.getLogger(__name__)

class ConnectionStatus(Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"

class ClientConnection(BaseModel):
    """Represents a WebSocket client connection"""
    model_config = {'arbitrary_types_allowed': True}
    
    client_id: str
    websocket: WebSocket
    connected_at: float
    last_activity: float
    status: ConnectionStatus
    metadata: Dict[str, Any] = {}

class WebSocketMessage(BaseModel):
    """Standardized WebSocket message format"""
    type: str
    data: Dict[str, Any]
    client_id: Optional[str] = None
    timestamp: float = None
    
    def __init__(self, **data):
        if 'timestamp' not in data:
            data['timestamp'] = time.time()
        super().__init__(**data)

MessageHandler = Callable[[WebSocketMessage, ClientConnection], Awaitable[Result[Optional[WebSocketMessage], str]]]

class WebSocketConnectionManager:
    """Manages WebSocket connections and message routing"""
    
    def __init__(self):
        self._connections: Dict[str, ClientConnection] = {}
        self._active_websockets: Set[WebSocket] = set()
        self._message_handlers: Dict[str, MessageHandler] = {}
        self._connection_listeners: Set[Callable[[ClientConnection, ConnectionStatus], Awaitable[None]]] = set()
    
    async def connect_client(self, websocket: WebSocket, metadata: Dict[str, Any] = None) -> Result[ClientConnection, str]:
        """Accept a new WebSocket connection and register the client"""
        try:
            await websocket.accept()
            client_id = str(uuid.uuid4())
            
            connection = ClientConnection(
                client_id=client_id,
                websocket=websocket,
                connected_at=time.time(),
                last_activity=time.time(),
                status=ConnectionStatus.CONNECTED,
                metadata=metadata or {}
            )
            
            self._connections[client_id] = connection
            self._active_websockets.add(websocket)
            
            logger.info(f"WebSocket client {client_id} connected from {self._get_client_info(websocket)}")
            
            # Send welcome message
            welcome_msg = WebSocketMessage(
                type="connection",
                data={
                    "status": "connected",
                    "client_id": client_id,
                    "message": "Ready for communication"
                }
            )
            await self._send_message(connection, welcome_msg)
            
            # Notify listeners
            await self._notify_connection_listeners(connection, ConnectionStatus.CONNECTED)
            
            return Success(connection)
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket client: {e}")
            return Failure(f"Connection failed: {str(e)}")
    
    async def disconnect_client(self, client_id: str, code: int = 1000, reason: str = "Normal closure") -> Result[None, str]:
        """Disconnect a client and clean up resources"""
        connection = self._connections.get(client_id)
        if not connection:
            return Failure(f"Client {client_id} not found")
        
        try:
            # Update connection status
            connection.status = ConnectionStatus.DISCONNECTED
            
            # Close WebSocket if still active
            if connection.websocket in self._active_websockets:
                try:
                    await connection.websocket.close(code, reason)
                except:
                    pass  # WebSocket might already be closed
            
            # Clean up
            self._active_websockets.discard(connection.websocket)
            del self._connections[client_id]
            
            logger.info(f"WebSocket client {client_id} disconnected: {reason}")
            
            # Notify listeners
            await self._notify_connection_listeners(connection, ConnectionStatus.DISCONNECTED)
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error disconnecting client {client_id}: {e}")
            return Failure(f"Disconnect failed: {str(e)}")
    
    async def send_message(self, client_id: str, message: WebSocketMessage) -> Result[None, str]:
        """Send a message to a specific client"""
        connection = self._connections.get(client_id)
        if not connection:
            return Failure(f"Client {client_id} not found")
        
        return await self._send_message(connection, message)
    
    async def broadcast_message(self, message: WebSocketMessage, exclude_clients: Set[str] = None) -> Result[int, str]:
        """Broadcast a message to all connected clients"""
        exclude_clients = exclude_clients or set()
        sent_count = 0
        
        for client_id, connection in self._connections.items():
            if client_id not in exclude_clients and connection.status == ConnectionStatus.CONNECTED:
                result = await self._send_message(connection, message)
                if result.is_success():
                    sent_count += 1
        
        logger.debug(f"Broadcast message sent to {sent_count} clients")
        return Success(sent_count)
    
    async def handle_client_messages(self, client_id: str) -> Result[None, str]:
        """Main message handling loop for a client"""
        connection = self._connections.get(client_id)
        if not connection:
            return Failure(f"Client {client_id} not found")
        
        try:
            while connection.status == ConnectionStatus.CONNECTED:
                try:
                    # Receive message from client
                    data = await connection.websocket.receive_json()
                    message = WebSocketMessage(
                        type=data.get("type", "unknown"),
                        data=data,
                        client_id=client_id
                    )
                    
                    # Update activity timestamp
                    connection.last_activity = time.time()
                    
                    # Process message
                    await self._process_message(message, connection)
                    
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error processing message from client {client_id}: {e}")
                    
                    # Send error response
                    error_msg = WebSocketMessage(
                        type="error",
                        data={"message": f"Message processing failed: {str(e)}"}
                    )
                    await self._send_message(connection, error_msg)
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Message handling failed for client {client_id}: {e}")
            return Failure(f"Message handling failed: {str(e)}")
    
    def register_message_handler(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for a specific message type"""
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")
    
    def add_connection_listener(self, listener: Callable[[ClientConnection, ConnectionStatus], Awaitable[None]]) -> None:
        """Add a listener for connection status changes"""
        self._connection_listeners.add(listener)
    
    def get_connection(self, client_id: str) -> Optional[ClientConnection]:
        """Get connection information for a client"""
        return self._connections.get(client_id)
    
    def get_active_connections(self) -> Dict[str, ClientConnection]:
        """Get all active connections"""
        return {
            client_id: conn for client_id, conn in self._connections.items()
            if conn.status == ConnectionStatus.CONNECTED
        }
    
    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len([conn for conn in self._connections.values() if conn.status == ConnectionStatus.CONNECTED])
    
    async def cleanup_stale_connections(self, max_idle_time: float = 300.0) -> Result[int, str]:
        """Clean up connections that have been idle for too long"""
        try:
            current_time = time.time()
            stale_clients = []
            
            for client_id, connection in self._connections.items():
                if (current_time - connection.last_activity) > max_idle_time:
                    stale_clients.append(client_id)
            
            # Disconnect stale clients
            for client_id in stale_clients:
                await self.disconnect_client(client_id, code=1001, reason="Connection idle timeout")
            
            if stale_clients:
                logger.info(f"Cleaned up {len(stale_clients)} stale connections")
            
            return Success(len(stale_clients))
            
        except Exception as e:
            logger.error(f"Error cleaning up stale connections: {e}")
            return Failure(f"Cleanup failed: {str(e)}")
    
    async def shutdown(self) -> Result[None, str]:
        """Shutdown the connection manager and close all connections"""
        try:
            # Disconnect all clients
            client_ids = list(self._connections.keys())
            for client_id in client_ids:
                await self.disconnect_client(client_id, code=1001, reason="Server shutdown")
            
            # Clear all data structures
            self._connections.clear()
            self._active_websockets.clear()
            self._message_handlers.clear()
            self._connection_listeners.clear()
            
            logger.info("WebSocket connection manager shutdown complete")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            return Failure(f"Shutdown failed: {str(e)}")
    
    async def _send_message(self, connection: ClientConnection, message: WebSocketMessage) -> Result[None, str]:
        """Internal method to send message to a connection"""
        try:
            if connection.websocket not in self._active_websockets:
                return Failure("WebSocket connection is not active")
            
            message_dict = message.dict()
            await connection.websocket.send_json(message_dict)
            
            logger.debug(f"Sent message type '{message.type}' to client {connection.client_id}")
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to send message to client {connection.client_id}: {e}")
            
            # Mark connection as errored and remove from active set
            connection.status = ConnectionStatus.ERROR
            self._active_websockets.discard(connection.websocket)
            
            return Failure(f"Send failed: {str(e)}")
    
    async def _process_message(self, message: WebSocketMessage, connection: ClientConnection) -> Result[None, str]:
        """Process an incoming message using registered handlers"""
        handler = self._message_handlers.get(message.type)
        if not handler:
            logger.warning(f"No handler for message type '{message.type}' from client {connection.client_id}")
            return Failure(f"Unknown message type: {message.type}")
        
        try:
            result = await handler(message, connection)
            
            # Send response if handler returned a message
            if result.is_success() and result.get_value():
                response = result.get_value()
                return await self._send_message(connection, response)
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Handler error for message type '{message.type}': {e}")
            return Failure(f"Handler failed: {str(e)}")
    
    async def _notify_connection_listeners(self, connection: ClientConnection, status: ConnectionStatus) -> None:
        """Notify all connection listeners about status changes"""
        for listener in self._connection_listeners:
            try:
                await listener(connection, status)
            except Exception as e:
                logger.error(f"Connection listener error: {e}")
    
    def _get_client_info(self, websocket: WebSocket) -> str:
        """Get client information from WebSocket for logging"""
        try:
            client_info = websocket.client
            return f"{client_info.host}:{client_info.port}" if client_info else "unknown"
        except:
            return "unknown"