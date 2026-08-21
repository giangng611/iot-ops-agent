import unittest

from scripts.check_mongodb_permissions import evaluate_runtime_privileges


class MongoDbPermissionTests(unittest.TestCase):
    def test_accepts_authenticated_collection_scoped_runtime_actions(self):
        result = evaluate_runtime_privileges(
            {
                "authInfo": {
                    "authenticatedUsers": [
                        {"user": "runtime", "db": "iot_ops_agent"},
                    ],
                    "authenticatedUserPrivileges": [
                        {
                            "resource": {
                                "db": "iot_ops_agent",
                                "collection": "telemetry",
                            },
                            "actions": [
                                "find",
                                "insert",
                                "listIndexes",
                                "update",
                            ],
                        },
                    ],
                },
            },
            "iot_ops_agent",
            "telemetry",
        )

        self.assertTrue(result["secure"])
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["violations"], [])

    def test_rejects_anonymous_or_overprivileged_connections(self):
        anonymous = evaluate_runtime_privileges(
            {"authInfo": {}},
            "iot_ops_agent",
            "telemetry",
        )
        overprivileged = evaluate_runtime_privileges(
            {
                "authInfo": {
                    "authenticatedUsers": [
                        {"user": "runtime", "db": "iot_ops_agent"},
                    ],
                    "authenticatedUserPrivileges": [
                        {
                            "resource": {
                                "db": "iot_ops_agent",
                                "collection": "",
                            },
                            "actions": ["find", "remove"],
                        },
                    ],
                },
            },
            "iot_ops_agent",
            "telemetry",
        )

        self.assertFalse(anonymous["secure"])
        self.assertFalse(overprivileged["secure"])
        self.assertTrue(
            any("remove" in violation for violation in overprivileged["violations"])
        )
        self.assertTrue(
            any(
                "unexpected resource" in violation
                for violation in overprivileged["violations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
