import unittest
from unittest.mock import MagicMock, patch

from services import company_data_service


class CompanyPostgresSecurityTests(unittest.TestCase):
    def test_read_only_guardrails_are_applied_with_parameterized_timeout(self):
        cursor = MagicMock()

        with patch.dict(
            "os.environ",
            {"COMPANY_DB_STATEMENT_TIMEOUT_MS": "2500"},
        ):
            company_data_service.set_read_only_guardrails(cursor)

        self.assertEqual(
            cursor.execute.call_args_list[0].args,
            ("set transaction read only",),
        )
        self.assertEqual(
            cursor.execute.call_args_list[1].args,
            ("set local statement_timeout = %s", ("2500",)),
        )

    def test_postgres_preview_rejects_identifier_injection_before_connecting(self):
        injection_targets = (
            ("public; drop schema public cascade; --", "devices"),
            ("public", 'devices"; drop table users; --'),
        )

        with patch.object(
            company_data_service,
            "get_company_connection",
        ) as connection:
            for schema_name, table_name in injection_targets:
                with self.subTest(
                    schema_name=schema_name,
                    table_name=table_name,
                ):
                    with self.assertRaises(ValueError):
                        company_data_service.preview_company_table(
                            schema_name,
                            table_name,
                        )

        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
