
from django.urls import path

from .consumers import CuidadosEnfermeriaConsumer


websocket_urlpatterns = [
    path(
        "ws/cuidados/<int:id_paciente>/",
        CuidadosEnfermeriaConsumer.as_asgi(),
    ),
]
