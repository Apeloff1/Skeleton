import json
from skeleton.automation.ci_feedback import build_feedback
from skeleton.automation.ci_feedback_report import render
def test_report_is_machine_readable():
 f=build_feedback(head_sha="a"*40,runs=({"id":1,"name":"CI/CD","status":"completed","conclusion":"success"},),required=("CI/CD",),job_logs={})
 d=json.loads(render(f));assert d["green"] is True and d["head_sha"]=="a"*40
