"""Uploads limitados em memória, sem fallback do Django para arquivo temporário."""
from django.conf import settings
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload


class PDFEmMemoriaUploadHandler(MemoryFileUploadHandler):
    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        # O padrão usa o Content-Length para decidir gravar em disco. Aqui,
        # os bytes efetivamente recebidos limitam todos os arquivos do pedido.
        self.activated = True
        self.bytes_recebidos = 0

    def receive_data_chunk(self, raw_data, start):
        self.bytes_recebidos += len(raw_data)
        if self.bytes_recebidos > settings.MAX_PDF_UPLOAD_SIZE:
            self.request.pdf_upload_interrompido = True
            self.file.close()
            raise StopUpload(connection_reset=True)
        return super().receive_data_chunk(raw_data, start)
