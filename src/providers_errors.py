class ProviderUnavailable(Exception):
    """Sanitized provider failure; never contains credentials or upstream response bodies."""
