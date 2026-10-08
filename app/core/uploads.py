"""Keep guest multipart binaries in memory before document extraction too."""

from io import BytesIO

from flask import Request


class GuestUploadRequest(Request):
    def _get_file_stream(
        self, total_content_length, content_type, filename=None, content_length=None
    ):
        if self.path == "/api/v1/guest/resume/upload":
            # Werkzeug otherwise spills uploads over 500KB to a temp file.
            # The application-wide 11MiB request limit still bounds memory.
            return BytesIO()
        return super()._get_file_stream(
            total_content_length, content_type, filename, content_length
        )
