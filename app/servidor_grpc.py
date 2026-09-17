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
from app.services.inferencia_service import TextoInvalidoError, validar_texto

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
    ) from None


class ServicoInferencia(
    inferencia_pb2_grpc.InferenciaServicer
):
    def __init__(self) -> None:
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
    ) -> inferencia_pb2.RespostaPrever:
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
        request: inferencia_pb2.PedidoPrever,
        context: grpc.ServicerContext,
    ) -> inferencia_pb2.RespostaPrever:
        """
        Executa inferencia para um unico texto.
        """
        inicio = time.perf_counter()

        try:
            texto_validado = validar_texto(request.texto)
        except TextoInvalidoError as erro:
            logger.warning(
                "gRPC Prever texto invalido | erro=%s",
                erro,
            )

            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                str(erro),
            )
            raise

        try:
            resultado = self.modelo.prever(
                texto_validado,
            )

            tempo_ms = round(
                (time.perf_counter() - inicio) * 1000,
                2,
            )

            logger.info(
                "gRPC Prever | tamanho=%s | tempo_ms=%s",
                len(texto_validado),
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
            raise

    def PreverLote(
        self,
        request: inferencia_pb2.PedidoLote,
        context: grpc.ServicerContext,
    ) -> inferencia_pb2.RespostaLote:
        """
        Executa inferencia para varios textos.
        """
        inicio = time.perf_counter()

        try:
            textos_validados = [
                validar_texto(texto) for texto in request.textos
            ]
        except TextoInvalidoError as erro:
            logger.warning(
                "gRPC PreverLote texto invalido | erro=%s",
                erro,
            )

            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                str(erro),
            )
            raise

        try:
            resultados = [
                self._converter_resposta(
                    self.modelo.prever(texto)
                )
                for texto in textos_validados
            ]

            tempo_ms = round(
                (time.perf_counter() - inicio) * 1000,
                2,
            )

            logger.info(
                "gRPC PreverLote | quantidade=%s | tempo_ms=%s",
                len(textos_validados),
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
            raise


def servir(
    porta: int = 50051,
) -> None:
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