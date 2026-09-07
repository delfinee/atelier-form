"""Pagination shared by every list endpoint, so clients see one shape."""

from collections import OrderedDict
from math import ceil
from typing import cast

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100

    def get_paginated_response(self, data):
        limit = cast(int, self.get_page_size(self.request) or self.page_size)
        return Response(OrderedDict([
            ("items", data),
            ("page", self.page.number),
            ("limit", limit),
            ("total", self.page.paginator.count),
            ("pages", ceil(self.page.paginator.count / limit) or 1),
        ]))

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "items": schema,
                "page": {"type": "integer", "example": 1},
                "limit": {"type": "integer", "example": 20},
                "total": {"type": "integer", "example": 21},
                "pages": {"type": "integer", "example": 2},
            },
        }
