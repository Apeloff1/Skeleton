import pytest
from skeleton.ai.task_types import *
def test_unknown_and_ambiguous_are_conservative_generic():
 assert classify_task("do something unusual").task_type is TaskType.GENERIC
 assert classify_task("security release").task_type is TaskType.GENERIC
def test_task_type_never_grants_privilege():
 for t in TaskType: assert _profile(t).grants_privilege is False
def _profile(t):return classify_task({TaskType.GENERIC:"unknown",TaskType.RESEARCH:"research",TaskType.CODE_CHANGE:"implement code",TaskType.SECURITY:"security",TaskType.DATA_CHANGE:"database schema",TaskType.RELEASE:"release"}[t]).profile
def test_security_defaults_add_tests_but_not_authority():
 c=classify_task("fix security vulnerability");assert c.task_type is TaskType.SECURITY and "security" in c.profile.required_tests and not c.profile.grants_privilege
def test_invalid_label_fails_closed():
 with pytest.raises(ValueError):classify_task("")
def test_profile_cannot_be_forged_to_grant_privilege():
 with pytest.raises(ValueError):TaskProfile(TaskType.GENERIC,1,(),(),True)
