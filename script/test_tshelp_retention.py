import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("retention", Path(__file__).with_name("retain-tshelp-releases.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(n, ext="apk", prefix="development"):
    return dict(id=n, tag_name=f"{prefix}-0.4.{n}", draft=False,
                body="<!-- tshelp-retention:protected -->",
                assets=[dict(id=n*10, name=f"agent.{ext}", state="uploaded", size=1),
                        dict(id=n*10+1, name=f"agent.{ext}.sha256")])


class RetentionTests(unittest.TestCase):
    def test_numeric_order_combined_environments_ignores_protection(self):
        kept, deleted = module.plan([row(9), row(15), row(14), row(13, prefix="production")])
        self.assertEqual([tag for tag, _ in kept], ["development-0.4.15", "development-0.4.14", "production-0.4.13"])
        self.assertEqual(len(deleted), 2)

    def test_separate_platform_budgets(self):
        kept, deleted = module.plan([row(n) for n in range(1, 6)] + [row(20, "exe")])
        self.assertEqual(len(kept), 4)
        self.assertEqual(len(deleted), 4)

    def test_mixed_release_keeps_windows_metadata(self):
        old = row(1)
        old["assets"] += [dict(id=100, name="agent.exe", state="uploaded", size=1),
                         dict(id=101, name="windows.json"), dict(id=102, name="android.json")]
        _, deleted = module.plan([old, row(2), row(3), row(4)])
        self.assertEqual({a["name"] for _, a in deleted}, {"agent.apk", "agent.apk.sha256", "android.json"})

    def test_refuses_unknown_or_incomplete(self):
        invalid = row(1)
        invalid["tag_name"] = "unknown"
        with self.assertRaises(ValueError):
            module.plan([invalid])
        invalid = row(1)
        invalid["assets"][0]["state"] = "starter"
        with self.assertRaises(ValueError):
            module.plan([invalid])

    def test_no_deletion_below_three(self):
        self.assertEqual(module.plan([row(1), row(2)])[1], [])


if __name__ == "__main__":
    unittest.main()
