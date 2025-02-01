import uuid
from werkzeug.routing import BaseConverter, ValidationError

class UUID6Converter(BaseConverter):
    def to_python(self, value):
        try:
            return uuid.UUID(value)
        except ValueError:
            raise ValidationError()

    def to_url(self, value):
        return str(value)
