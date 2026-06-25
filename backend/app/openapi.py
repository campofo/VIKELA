OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "VIKELA Backend API",
        "version": "1.0.0",
        "description": "API for VIKELA mobile panic alerts, hardware alerts, responder contacts, notifications, and location anomaly results.",
    },
    "servers": [
        {"url": "http://YOUR_VPS_IP:8100", "description": "Docker/VPS deployment"},
        {"url": "http://localhost:8001", "description": "Local Flask development"},
    ],
    "paths": {
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {
                    "200": {
                        "description": "Backend is healthy",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/api/alerts/mobile": {
            "post": {
                "summary": "Send a mobile app panic alert",
                "description": "Use this endpoint from the mobile app. The backend stores the alert, runs location anomaly detection, and queues/sends responder notifications.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/MobileAlertRequest"},
                            "example": {
                                "device_id": "VIKELA-MOBILE-APP-001",
                                "user_id": "mobile-user-001",
                                "trigger_type": "mobile",
                                "latitude": 5.6037,
                                "longitude": -0.187,
                                "battery_level": 78,
                                "timestamp": "2026-06-25T16:00:00Z",
                                "message": "VIKELA MOBILE PANIC",
                            },
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Alert accepted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AlertAcceptedResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid alert payload",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                },
            }
        },
        "/api/alerts/hardware": {
            "post": {
                "summary": "Send a hardware panic alert",
                "description": "Used by the LILYGO T-SIM7000G firmware.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/HardwareAlertRequest"}
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Alert accepted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AlertAcceptedResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid alert payload",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                },
            }
        },
        "/api/alerts": {
            "get": {
                "summary": "List recent alerts",
                "parameters": [{"$ref": "#/components/parameters/Limit"}],
                "responses": {
                    "200": {
                        "description": "Recent alerts",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/AlertRecord"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/panic-contacts": {
            "get": {
                "summary": "List panic contacts",
                "responses": {
                    "200": {
                        "description": "Configured panic contacts",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/PanicContact"},
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "summary": "Add a panic contact number",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreatePanicContactRequest"},
                            "example": {
                                "phone_number": "+233000000000",
                                "name": "Primary responder",
                                "relationship": "family",
                                "enabled": True,
                            },
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Contact created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreatePanicContactResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid contact payload",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                },
            },
        },
        "/api/panic-contacts/numbers": {
            "get": {
                "summary": "List enabled panic contact phone numbers",
                "description": "Used by firmware and can also be used by the mobile app if it needs to display active responder numbers.",
                "responses": {
                    "200": {
                        "description": "Enabled phone numbers",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PanicContactNumbersResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/api/panic-contacts/{contact_id}": {
            "delete": {
                "summary": "Delete a panic contact",
                "parameters": [
                    {
                        "name": "contact_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Contact deleted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/DeleteResponse"}
                            }
                        },
                    },
                    "404": {
                        "description": "Contact not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/DeleteResponse"}
                            }
                        },
                    },
                },
            }
        },
        "/api/notifications": {
            "get": {
                "summary": "List responder notification attempts",
                "parameters": [{"$ref": "#/components/parameters/Limit"}],
                "responses": {
                    "200": {
                        "description": "Recent notification attempts",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/NotificationRecord"},
                                }
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "parameters": {
            "Limit": {
                "name": "limit",
                "in": "query",
                "required": False,
                "schema": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            }
        },
        "schemas": {
            "HealthResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "ok"},
                    "service": {"type": "string", "example": "vikela-backend"},
                },
                "required": ["status", "service"],
            },
            "MobileAlertRequest": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "example": "VIKELA-MOBILE-APP-001"},
                    "user_id": {"type": "string", "nullable": True, "example": "mobile-user-001"},
                    "trigger_type": {"type": "string", "enum": ["mobile"], "example": "mobile"},
                    "latitude": {"type": "number", "nullable": True, "minimum": -90, "maximum": 90},
                    "longitude": {"type": "number", "nullable": True, "minimum": -180, "maximum": 180},
                    "location_source": {"type": "string", "default": "mobile_gps"},
                    "delivery_attempt": {"type": "string", "default": "mobile_http"},
                    "battery_level": {"type": "number", "nullable": True, "example": 78},
                    "timestamp": {"type": "string", "nullable": True, "example": "2026-06-25T16:00:00Z"},
                    "message": {"type": "string", "example": "VIKELA MOBILE PANIC"},
                },
                "required": ["device_id", "message"],
            },
            "HardwareAlertRequest": {
                "allOf": [
                    {"$ref": "#/components/schemas/MobileAlertRequest"},
                    {
                        "type": "object",
                        "properties": {
                            "trigger_type": {"type": "string", "enum": ["hardware"]},
                            "location_source": {"type": "string", "default": "sim7000g_gps"},
                            "delivery_attempt": {"type": "string", "default": "cellular_http"},
                        },
                    },
                ]
            },
            "AlertAcceptedResponse": {
                "type": "object",
                "properties": {
                    "accepted": {"type": "boolean"},
                    "alert_id": {"type": "string"},
                    "status": {"type": "string", "example": "triage_pending"},
                    "received_at": {"type": "string", "example": "2026-06-25T16:00:00Z"},
                    "maps_url": {"type": "string", "nullable": True},
                    "location_anomaly": {"type": "boolean"},
                    "anomaly_level": {"type": "string", "enum": ["unknown", "baseline", "normal", "watch", "high", "critical"]},
                    "anomaly_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "anomaly_reasons": {"type": "array", "items": {"type": "string"}},
                    "distance_from_previous_km": {"type": "number", "nullable": True},
                    "speed_from_previous_kmh": {"type": "number", "nullable": True},
                    "notifications_created": {"type": "integer"},
                },
            },
            "AlertRecord": {
                "allOf": [
                    {"$ref": "#/components/schemas/MobileAlertRequest"},
                    {"$ref": "#/components/schemas/AlertAcceptedResponse"},
                ]
            },
            "PanicContact": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "phone_number": {"type": "string", "example": "+233000000000"},
                    "name": {"type": "string", "nullable": True},
                    "relationship": {"type": "string", "nullable": True},
                    "enabled": {"type": "boolean"},
                    "created_at": {"type": "string"},
                },
            },
            "CreatePanicContactRequest": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "example": "+233000000000"},
                    "name": {"type": "string", "nullable": True},
                    "relationship": {"type": "string", "nullable": True},
                    "enabled": {"type": "boolean", "default": True},
                },
                "required": ["phone_number"],
            },
            "CreatePanicContactResponse": {
                "type": "object",
                "properties": {
                    "created": {"type": "boolean"},
                    "contact": {"$ref": "#/components/schemas/PanicContact"},
                },
            },
            "PanicContactNumbersResponse": {
                "type": "object",
                "properties": {
                    "phone_numbers": {
                        "type": "array",
                        "items": {"type": "string", "example": "+233000000000"},
                    }
                },
            },
            "NotificationRecord": {
                "type": "object",
                "properties": {
                    "notification_id": {"type": "string"},
                    "alert_id": {"type": "string"},
                    "contact_id": {"type": "string"},
                    "phone_number": {"type": "string"},
                    "message": {"type": "string"},
                    "channel": {"type": "string", "example": "sms_webhook"},
                    "status": {"type": "string", "example": "queued_no_provider"},
                    "provider_status": {"type": "integer", "nullable": True},
                    "provider_response": {"type": "string", "nullable": True},
                    "created_at": {"type": "string"},
                },
            },
            "DeleteResponse": {
                "type": "object",
                "properties": {
                    "deleted": {"type": "boolean"},
                    "error": {"type": "string"},
                },
            },
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "accepted": {"type": "boolean", "example": False},
                    "created": {"type": "boolean", "example": False},
                    "error": {"type": "string"},
                },
            },
        },
    },
}
