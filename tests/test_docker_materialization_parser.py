"""Source-build custody regressions; script bodies cannot declare Docker stages."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import check_app_assembly, check_provider_bootstrap


class DockerMaterializationCustodyTests(unittest.TestCase):
    def test_script_import_and_copy_spoofs_never_become_materialization(self):
        source = """FROM python:3.14 AS production
WORKDIR /app
RUN python - <<'PYTHON'
from pathlib import Path
FROM attacker AS injected
COPY --from=runtime-source --chown=appuser:appuser /runtime/ .
PYTHON
RUN true
"""
        instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
        self.assertEqual([item["name"] for item in stages], ["production"])
        self.assertEqual(stages[0]["copies"], [])
        self.assertNotIn("FROM attacker AS injected", instructions)

    def test_real_copy_after_closed_script_retains_named_stage_custody(self):
        source = """FROM python:3.14 AS production
WORKDIR /app
RUN python - <<'PYTHON'
from pathlib import Path
PYTHON
COPY --from=runtime-source --chown=appuser:appuser /runtime/ .
FROM production AS development
"""
        _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
        self.assertEqual([item["name"] for item in stages], ["production", "development"])
        expected = [("COPY --from=runtime-source --chown=appuser:appuser /runtime/ .", "/app")]
        self.assertEqual(stages[0]["copies"], expected)
        self.assertEqual(stages[1]["copies"], expected)

    def test_unterminated_script_cannot_establish_any_stage(self):
        for closing in ("", " PYTHON", "\tPYTHON"):
            with self.subTest(closing=closing):
                source = "FROM python:3.14 AS production\nRUN python - <<'PYTHON'\n" + closing + "\nCOPY . .\n"
                _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
                self.assertEqual(stages, [])

    def test_tab_stripping_requires_explicit_heredoc_operator(self):
        source = "FROM python:3.14 AS production\nRUN <<-SCRIPT\n\tFROM attacker\n\tSCRIPT\nCOPY . .\n"
        _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
        self.assertEqual([item["name"] for item in stages], ["production"])
        self.assertEqual(stages[0]["copies"], [("COPY . .", "/")])

    def test_unsupported_or_multiple_heredocs_cannot_fabricate_copy_custody(self):
        for opener, body in (("RUN <<FIRST <<SECOND", "FIRST\nCOPY . .\nSECOND"),
                             ("RUN <<123", "COPY . .\n123")):
            with self.subTest(opener=opener):
                source = "FROM python:3.14 AS production\n" + opener + "\n" + body + "\n"
                _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
                self.assertEqual(stages, [])

    def test_delimiter_prefix_never_ends_the_actual_heredoc(self):
        for opener, terminator in (("RUN cat <<END-DOC", "END-DOC"),
                                   ("RUN cat <<END#DOC", "END#DOC"),
                                   ("RUN cat <<'END'DOC", "ENDDOC")):
            with self.subTest(opener=opener):
                source = ("FROM python:3.14 AS production\nWORKDIR /app\n" + opener +
                          "\nEND\nCOPY --from=runtime-source --chown=appuser:appuser /runtime/ .\n" +
                          terminator + "\n")
                _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
                self.assertEqual(stages, [])

    def test_repository_backend_stages_survive_embedded_python(self):
        source = (Path(__file__).resolve().parents[1] / "backend/Dockerfile").read_text()
        _instructions, stages = check_provider_bootstrap._docker_materialization_stages(source)
        self.assertEqual([item["name"] for item in stages],
                         ["builder", "runtime-source", "production", "development"])
        production = stages[2]
        self.assertIn(("COPY --from=runtime-source --chown=appuser:appuser /runtime/ .", "/app"),
                      production["copies"])


class FrontendLoopbackAssemblyTests(unittest.TestCase):
    def test_assembly_check_rejects_wildcard_and_unqualified_frontend_bindings(self):
        read = check_app_assembly.read
        source = read("docker-compose.yml")
        expected = '"127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}"'
        self.assertIn(expected, source)
        for replacement, denied in ((expected, False),
                                    (expected.replace("127.0.0.1:", ""), True),
                                    (expected.replace("127.0.0.1", "0.0.0.0"), True)):
            with self.subTest(binding=replacement):
                previous_failures = check_app_assembly.FAILURES
                previous_checks = check_app_assembly.CHECKS
                try:
                    check_app_assembly.FAILURES = []
                    check_app_assembly.CHECKS = 0
                    def replacement_read(relative):
                        return source.replace(expected, replacement) if relative == "docker-compose.yml" else read(relative)
                    with patch.object(check_app_assembly, "read", side_effect=replacement_read), \
                         patch.object(check_app_assembly, "_backend_local_provider_consumers", return_value=()):
                        check_app_assembly.audit_compose_modes()
                    self.assertEqual("frontend container port must be assembly-selectable" in
                                     check_app_assembly.FAILURES, denied)
                finally:
                    check_app_assembly.FAILURES = previous_failures
                    check_app_assembly.CHECKS = previous_checks


if __name__ == "__main__":
    unittest.main()
