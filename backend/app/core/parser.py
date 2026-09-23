import hashlib


PARSER_CONFIG_VERSION = "docling-v1-text-table"

PARSER_CONFIG_HASH = hashlib.sha256(
    PARSER_CONFIG_VERSION.encode("utf-8")
).hexdigest()
