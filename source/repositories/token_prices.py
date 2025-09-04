from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine


class TokenPricesRepository:
    _engine: Engine

    def __init__(self, engine: Engine):
        self._engine = engine

    def get_latest_token_prices(self) -> tuple[Decimal, Decimal] | None:
        """
        Fetches the most recent token prices from the database.
        """
        with self._engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                SELECT input_price_per_1k_tokens, output_price_per_1k_tokens
                FROM token_prices
                ORDER BY created_at DESC
                LIMIT 1
                """
                )
            ).first()

            if result:
                return result.input_price_per_1k_tokens, result.output_price_per_1k_tokens
            return None

    def insert_token_price(self, input_price: Decimal, output_price: Decimal) -> None:
        """
        Inserts a new token price into the database.
        """
        with self._engine.connect() as connection:
            connection.execute(
                text(
                    """
                INSERT INTO token_prices (input_price_per_1k_tokens, output_price_per_1k_tokens)
                VALUES (:input_price, :output_price)
                """
                ),
                {"input_price": input_price, "output_price": output_price},
            )
