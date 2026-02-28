# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Kiro Gateway - Proxy for Kiro API.

This package provides a modular architecture for proxying
API requests to Kiro (AWS CodeWhisperer).

Package Structure:
    - core/: Core functionality (auth, cache, config, model resolution, HTTP client)
    - routes/: API route handlers
    - models/: Pydantic data models
    - converters/: Format conversion logic
    - streaming/: Response streaming handlers
    - utils_pkg/: Utility functions and helpers
    - middleware/: FastAPI middleware components
"""

# Version is imported from config.py — the single source of truth
from kiro.core.config import APP_VERSION as __version__

__author__ = "Jwadow"

# Main components for convenient import
from kiro.core.auth import AccountManager
from kiro.core.cache import ModelInfoCache
from kiro.core.http_client import KiroHttpClient
from kiro.core.model_resolver import ModelResolver, normalize_model_name, get_model_id_for_kiro

# Configuration
from kiro.core.config import (
    PROXY_API_KEY,
    REGION,
    HIDDEN_MODELS,
    APP_VERSION,
)

# Converters
from kiro.converters.core import (
    extract_text_content,
    merge_adjacent_messages,
)

# Parsers
from kiro.utils_pkg.parsers import (
    AwsEventStreamParser,
    parse_bracket_tool_calls,
)

# Streaming
from kiro.streaming.api import (
    stream_kiro_to_anthropic,
    collect_anthropic_response,
)

# Exceptions
from kiro.middleware.exceptions import (
    validation_exception_handler,
    sanitize_validation_errors,
)

__all__ = [
    # Version
    "__version__",
    
    # Main classes
    "AccountManager",
    "ModelInfoCache",
    "KiroHttpClient",
    "ModelResolver",
    
    # Configuration
    "PROXY_API_KEY",
    "REGION",
    "HIDDEN_MODELS",
    "APP_VERSION",
    
    # Model resolution
    "normalize_model_name",
    "get_model_id_for_kiro",
    
    # Converters
    "extract_text_content",
    "merge_adjacent_messages",
    
    # Parsers
    "AwsEventStreamParser",
    "parse_bracket_tool_calls",
    
    # Streaming
    "stream_kiro_to_anthropic",
    "collect_anthropic_response",
    
    # Exceptions
    "validation_exception_handler",
    "sanitize_validation_errors",
]
