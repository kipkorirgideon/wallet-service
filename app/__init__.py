import os

from flask import Flask, jsonify, request

from .auth import build_context
from .db import Base, SessionLocal, engine
from .schema import schema


def create_app():
    app = Flask(__name__)

    # Base.metadata.create_all(engine)

    @app.post("/graphql")
    def graphql_view():
        session = SessionLocal()
        try:
            payload = request.get_json(force=True)
            context = build_context(session, request)
            result = schema.execute_sync(
                payload.get("query"),
                variable_values=payload.get("variables"),
                context_value=context,
            )
            response = {"data": result.data}
            if result.errors:
                response["errors"] = [str(e) for e in result.errors]
            return jsonify(response)
        finally:
            session.close()

    return app
