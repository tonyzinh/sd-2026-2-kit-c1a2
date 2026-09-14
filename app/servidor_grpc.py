"""
Interface gRPC do servico de inferencia.

PRE-REQUISITO:
Gerar os stubs antes de rodar.

O QUE JA ESTA PRONTO:
- metodo Prever

TAREFA:
- implementar PreverLote

Rodar:
    python -m app.servidor_grpc
"""

from concurrent import futures

import grpc

from app.modelo import carregar_modelo

try:
    import inferencia_pb2
    import inferencia_pb2_grpc
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Stubs nao encontrados. Rode antes:\n"
        "  python -m grpc_tools.protoc -I proto --python_out=. "
        "--grpc_python_out=. proto/inferencia.proto"
    )


class ServicoInferencia(
    inferencia_pb2_grpc.InferenciaServicer
):
    def __init__(self):
        print("[grpc] carregando modelo...")
        self.modelo = carregar_modelo()
        print("[grpc] modelo pronto")

    def _converter_resposta(self, resultado: dict):
        """Converte o resultado do modelo para a resposta protobuf."""
        return inferencia_pb2.RespostaPrever(
            texto=resultado["texto"],
            sentimento=resultado["sentimento"],
            confianca=resultado["confianca"],
        )

    def Prever(self, request, context):
        """Executa inferencia de um unico texto."""
        resultado = self.modelo.prever(request.texto)

        return self._converter_resposta(resultado)

    def PreverLote(self, request, context):
        """Executa inferencia para varios textos."""
        resultados = [
            self._converter_resposta(
                self.modelo.prever(texto)
            )
            for texto in request.textos
        ]

        return inferencia_pb2.RespostaLote(
            resultados=resultados
        )


def servir(porta: int = 50051):
    servidor = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=10
        )
    )

    inferencia_pb2_grpc.add_InferenciaServicer_to_server(
        ServicoInferencia(),
        servidor,
    )

    servidor.add_insecure_port(
        f"[::]:{porta}"
    )

    servidor.start()

    print(
        f"[grpc] escutando na porta {porta}"
    )

    servidor.wait_for_termination()


if __name__ == "__main__":
    servir()