"""
gameforge.workflow — Autonomous Game-Dev Workflow (Cowabunga v4 adaptation).

Self-contained, dependency-light modules adapted from the uploaded
gameforge_mega_cowabunga_v4 standalone package so they fit THIS backend
(Mongo-persisted, reusing the existing encrypted boardroom_vault) instead
of importing the missing orchestration.* / governance.* / utils.* modules.

Public surface:
    autonomous_workflow.autonomous_workflow  — the Prompt→…→Deployment engine
    internal_build_system.InternalBuildSystem — self-contained build/package
    jeeves_vault.jeeves_vault                — package registry + delivery links
    workflow_persistence.workflow_persistence — resumable run state (Mongo)
"""
