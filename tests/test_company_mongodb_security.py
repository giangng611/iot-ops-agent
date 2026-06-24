import unittest

from scripts.check_company_mongodb_security import (
    evaluate_company_privileges,
)


ALLOWED_NAMESPACES = {
    "authorization.IDENTITY",
    "datamgmt.CIN",
    "datamgmt.CNT",
    "datamgmt.DEVICE_TELEMETRY",
    "datamgmt.RULE",
    "devicemgmt.NODE",
    "orchestration.URI_MAPPER",
    "subNNotif.AE",
    "subNNotif.SUB",
}


class CompanyMongoDbSecurityTests(unittest.TestCase):
    def test_accepts_database_scoped_read_only_privileges(self):
        status = {
            "authInfo": {
                "authenticatedUsers": [
                    {"user": "company_reader", "db": "admin"},
                ],
                "authenticatedUserRoles": [
                    {"role": "companyIoTReader", "db": "admin"},
                ],
                "authenticatedUserPrivileges": [
                    {
                        "resource": {
                            "db": "datamgmt",
                            "collection": "CIN",
                        },
                        "actions": ["find", "listIndexes"],
                    },
                ],
            },
        }

        result = evaluate_company_privileges(
            status,
            ALLOWED_NAMESPACES,
        )

        self.assertTrue(result["least_privilege"])
        self.assertEqual(result["violations"], [])

    def test_rejects_read_any_database_and_write_actions(self):
        status = {
            "authInfo": {
                "authenticatedUsers": [
                    {"user": "adminread", "db": "admin"},
                ],
                "authenticatedUserRoles": [
                    {"role": "readAnyDatabase", "db": "admin"},
                ],
                "authenticatedUserPrivileges": [
                    {
                        "resource": {"db": "", "collection": ""},
                        "actions": ["find", "insert"],
                    },
                ],
            },
        }

        result = evaluate_company_privileges(
            status,
            ALLOWED_NAMESPACES,
        )

        self.assertFalse(result["least_privilege"])
        self.assertTrue(any(
            "readAnyDatabase" in violation
            for violation in result["violations"]
        ))
        self.assertTrue(any(
            "insert" in violation
            for violation in result["violations"]
        ))


if __name__ == "__main__":
    unittest.main()
