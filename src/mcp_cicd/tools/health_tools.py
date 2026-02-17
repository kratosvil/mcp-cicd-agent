# Este archivo implementa la herramienta MCP para verificación de salud de servicios:
# healthcheck con retry exponencial y timeout configurable.

"""
MCP tools for service health checking.

Implements healthcheck tool with exponential backoff.
"""
import time  # Funciones de tiempo para sleep y medición de elapsed time
from typing import Optional  # Type hints para valores opcionales

import httpx  # Cliente HTTP async para health checks
from mcp.server.fastmcp import FastMCP  # Framework FastMCP para registro de herramientas

from ..config.settings import get_settings  # Singleton de configuración
from ..utils.logging import get_logger  # Logger estructurado
from ..exceptions import HealthCheckError  # Excepción personalizada para health checks

logger = get_logger(__name__)
settings = get_settings()


def register_health_tools(mcp: FastMCP) -> None:
    """
    Register health check MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def healthcheck(
        url: str,
        timeout: Optional[int] = None,
        interval: float = 2.0,
        backoff: float = 1.5,
        expected_status: int = 200
    ) -> dict:
        """
        Validate service availability with exponential backoff retry.

        Polls the specified URL until it returns the expected HTTP status code
        or the timeout is reached. Uses exponential backoff between retries to
        avoid overwhelming the service during startup.

        Retry strategy:
        - Initial interval: 2.0 seconds (configurable)
        - Backoff multiplier: 1.5 (configurable)
        - Max interval: 10 seconds
        - Total timeout: 30 seconds (configurable)

        Args:
            url: URL to check (e.g., http://localhost:8080/ or http://localhost:8080/health)
            timeout: Maximum seconds to wait (default: from settings, typically 30)
            interval: Initial retry interval in seconds (default: 2.0)
            backoff: Backoff multiplier for retry interval (default: 1.5)
            expected_status: Expected HTTP status code (default: 200)

        Returns:
            Dictionary containing:
                - healthy: Boolean indicating if service is healthy
                - url: URL that was checked
                - response_code: HTTP status code (if successful)
                - attempts: Number of attempts made
                - elapsed_seconds: Total time elapsed
                - message: Human-readable status message
                - error: Error message (if unhealthy)
        """
        try:
            logger.info(
                "healthcheck_started",
                url=url,
                timeout=timeout,
                expected_status=expected_status
            )

            # Use configured timeout if not specified
            max_timeout = timeout if timeout is not None else settings.health_check_timeout

            # Track timing using monotonic clock (immune to system clock changes)
            start_time = time.monotonic()
            attempt = 0
            current_interval = interval

            last_error = None
            last_status_code = None

            while (time.monotonic() - start_time) < max_timeout:
                attempt += 1

                try:
                    logger.debug(
                        "healthcheck_attempt",
                        attempt=attempt,
                        url=url
                    )

                    # Make HTTP request with short timeout
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            url,
                            timeout=5.0,
                            follow_redirects=True
                        )

                    last_status_code = response.status_code

                    # Check if status matches expected
                    if response.status_code == expected_status:
                        elapsed = round(time.monotonic() - start_time, 2)

                        result = {
                            "healthy": True,
                            "url": url,
                            "response_code": response.status_code,
                            "attempts": attempt,
                            "elapsed_seconds": elapsed,
                            "message": f"Service healthy after {attempt} attempt(s) in {elapsed}s"
                        }

                        logger.info(
                            "healthcheck_success",
                            url=url,
                            attempts=attempt,
                            elapsed=elapsed
                        )

                        return result

                    else:
                        last_error = f"Unexpected status code: {response.status_code}"
                        logger.debug(
                            "healthcheck_unexpected_status",
                            url=url,
                            status_code=response.status_code,
                            expected=expected_status
                        )

                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    last_error = str(e)
                    logger.debug(
                        "healthcheck_connection_failed",
                        url=url,
                        attempt=attempt,
                        error=str(e)
                    )

                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "healthcheck_unexpected_error",
                        url=url,
                        attempt=attempt,
                        error=str(e)
                    )

                # Wait before next attempt (exponential backoff with cap)
                time.sleep(min(current_interval, 10.0))
                current_interval *= backoff

            # Timeout reached - service unhealthy
            elapsed = round(time.monotonic() - start_time, 2)

            result = {
                "healthy": False,
                "url": url,
                "response_code": last_status_code,
                "attempts": attempt,
                "elapsed_seconds": elapsed,
                "message": f"Service unhealthy after {attempt} attempt(s) in {elapsed}s",
                "error": last_error or "Timeout reached"
            }

            logger.error(
                "healthcheck_timeout",
                url=url,
                attempts=attempt,
                elapsed=elapsed,
                last_error=last_error
            )

            raise HealthCheckError(
                f"Health check failed for {url}: {last_error or 'timeout'}",
                context={
                    "url": url,
                    "attempts": attempt,
                    "elapsed": elapsed,
                    "last_error": last_error
                }
            )

        except HealthCheckError:
            # Re-raise health check errors
            raise

        except Exception as e:
            logger.error(
                "healthcheck_failed",
                url=url,
                error=str(e)
            )
            raise HealthCheckError(
                f"Health check error: {e}",
                context={"url": url, "error": str(e)}
            )
