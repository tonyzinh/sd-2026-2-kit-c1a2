"""
Interface gRPC do servico de inferencia.

PRE-REQUISITO:
Gerar os stubs antes de rodar.

Comando:
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=. \
        --grpc_python_out=. \
        proto/inferencia.proto

Rodar:
    python -m app.servidor_grpc
"""

import logging
import time
from concurrent import futures

import grpc

from app.modelo import carregar_modelo


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


try:
    import inferencia_pb2
    import inferencia_pb2_grpc
except ImportError:
    raise SystemExit(
        "Stubs nao encontrados. Rode antes:\n"
        "python -m grpc_tools.protoc "
        "-I proto "
        "--python_out=. "
        "--grpc_python_out=. "
        "proto/inferencia.proto"
    )


class ServicoInferencia(
    inferencia_pb2_grpc.InferenciaServicer
):
    def __init__(self):
        """
        Carrega o modelo uma unica vez na inicializacao do servidor.
        """
        logger.info(
            "gRPC carregando modelo",
        )

        self.modelo = carregar_modelo()

        logger.info(
            "gRPC modelo pronto",
        )

    def _converter_resposta(
        self,
        resultado: dict,
    ):
        """
        Converte o resultado do modelo para mensagem protobuf.
        """
        return inferencia_pb2.RespostaPrever(
            texto=resultado["texto"],
            sentimento=resultado["sentimento"],
            confianca=resultado["confianca"],
        )

    def Prever(
        self,
        request,
        context,
    ):
        """
        Executa inferencia para um unico texto.
        """
        inicio = time.perf_counter()

        try:
            resultado = self.modelo.prever(
                request.texto,
            )

            tempo_ms = round(
                (time.perf_counter() - inicio) * 1000,
                2,
            )

            logger.info(
                "gRPC Prever | tamanho=%s | tempo_ms=%s",
                len(request.texto),
                tempo_ms,
            )

            return self._converter_resposta(
                resultado,
            )

        except Exception as erro:
            logger.exception(
                "gRPC Prever falhou | erro=%s",
                erro,
            )

            context.abort(
                grpc.StatusCode.INTERNAL,
                "Falha ao processar inferencia.",
            )

    def PreverLote(
        self,
        request,
        context,
    ):
        """
        Executa inferencia para varios textos.
        """
        inicio = time.perf_counter()

        try:
            resultados = [
                self._converter_resposta(
                    self.modelo.prever(texto)
                )
                for texto in request.textos
            ]

            tempo_ms = round(
                (time.perf_counter() - inicio) * 1000,
                2,
            )

            logger.info(
                "gRPC PreverLote | quantidade=%s | tempo_ms=%s",
                len(request.textos),
                tempo_ms,
            )

            return inferencia_pb2.RespostaLote(
                resultados=resultados,
            )

        except Exception as erro:
            logger.exception(
                "gRPC PreverLote falhou | erro=%s",
                erro,
            )

            context.abort(
                grpc.StatusCode.INTERNAL,
                "Falha ao processar lote.",
            )


def servir(
    porta: int = 50051,
):
    """
    Inicializa e mantem o servidor gRPC em execucao.
    """
    servidor = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=10,
        )
    )

    inferencia_pb2_grpc.add_InferenciaServicer_to_server(
        ServicoInferencia(),
        servidor,
    )

    servidor.add_insecure_port(
        f"[::]:{porta}",
    )

    servidor.start()

    logger.info(
        "gRPC servidor escutando | porta=%s",
        porta,
    )

    servidor.wait_for_termination()


if __name__ == "__main__":
    servir()