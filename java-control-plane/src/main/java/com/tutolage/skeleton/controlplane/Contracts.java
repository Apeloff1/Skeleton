package com.tutolage.skeleton.controlplane;

import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/** Typed wire and runtime contracts shared by the Java control plane. */
public final class Contracts {
    private Contracts() {}

    public enum Capability {
        READ_STATE,
        WRITE_STATE,
        NETWORK,
        EXECUTE,
        FILE_READ,
        FILE_WRITE,
        MODEL_INVOKE,
        SECRET_READ,
        ARTIFACT_WRITE,
        METRICS_WRITE
    }

    public enum Risk { LOW, MEDIUM, HIGH, CRITICAL }
    public enum TaskStatus { ACCEPTED, RUNNING, SUCCEEDED, FAILED, DENIED, CANCELLED, TIMED_OUT }
    public enum EvidenceKind { INPUT_DIGEST, POLICY_DECISION, NETWORK_CALL, TOOL_CALL, OUTPUT_DIGEST, ERROR, CHECKPOINT, METRIC, AUDIT }
    public enum DecisionKind { ALLOW, DENY, REQUIRE_REVIEW }

    public record Bounds(
        int maxPromptChars,
        int maxOutputChars,
        int maxEvidenceItems,
        int maxAttempts,
        Duration timeout
    ) {
        public Bounds {
            if (maxPromptChars < 1 || maxOutputChars < 1 || maxEvidenceItems < 0 || maxAttempts < 1) {
                throw new IllegalArgumentException("invalid bounds");
            }
            Objects.requireNonNull(timeout, "timeout");
            if (timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("timeout");
        }

        public static Bounds defaults() {
            return new Bounds(200_000, 1_000_000, 10_000, 3, Duration.ofMinutes(5));
        }
    }

    public record Identity(String subject, String tenant, Set<String> roles) {
        public Identity {
            subject = bounded(subject, "subject", 1, 256);
            tenant = bounded(tenant, "tenant", 1, 256);
            roles = Set.copyOf(roles);
        }

        public boolean hasRole(String role) { return roles.contains(role); }

        public Json.Obj toJson() {
            return Json.obj(
                "subject", subject,
                "tenant", tenant,
                "roles", roles.stream().sorted().toList()
            );
        }

        public static Identity fromJson(Json.Obj o) {
            o.rejectUnknown("subject", "tenant", "roles");
            var roles = new java.util.LinkedHashSet<String>();
            for (var v : o.array("roles").values()) {
                roles.add(Json.expectString(v, "$.roles[]"));
            }
            return new Identity(o.string("subject"), o.string("tenant"), roles);
        }
    }

    public record TaskRequest(
        String taskId,
        String kind,
        String prompt,
        Json.Obj input,
        Identity identity,
        Set<Capability> requestedCapabilities,
        Risk risk,
        Bounds bounds,
        Instant createdAt,
        String correlationId,
        Map<String, String> tags
    ) {
        public TaskRequest {
            Objects.requireNonNull(bounds, "bounds");
            taskId = identifier(taskId, "taskId");
            kind = bounded(kind, "kind", 1, 128);
            prompt = bounded(prompt, "prompt", 0, bounds.maxPromptChars());
            Objects.requireNonNull(input, "input");
            Objects.requireNonNull(identity, "identity");
            requestedCapabilities = Set.copyOf(requestedCapabilities);
            Objects.requireNonNull(risk, "risk");
            Objects.requireNonNull(createdAt, "createdAt");
            correlationId = identifier(correlationId, "correlationId");
            tags = boundedMap(tags, "tags", 64, 128, 1024);
        }

        public static TaskRequest create(String kind, String prompt, Identity identity) {
            return new TaskRequest(
                UUID.randomUUID().toString(),
                kind,
                prompt,
                Json.obj(),
                identity,
                Set.of(),
                Risk.LOW,
                Bounds.defaults(),
                Instant.now(),
                UUID.randomUUID().toString(),
                Map.of()
            );
        }

        public Json.Obj toJson() {
            return Json.obj(
                "task_id", taskId,
                "kind", kind,
                "prompt", prompt,
                "input", input,
                "identity", identity.toJson(),
                "capabilities", requestedCapabilities.stream().map(Enum::name).sorted().toList(),
                "risk", risk.name(),
                "bounds", boundsToJson(bounds),
                "created_at", createdAt.toString(),
                "correlation_id", correlationId,
                "tags", tags
            );
        }

        public static TaskRequest fromJson(Json.Obj o) {
            o.rejectUnknown(
                "task_id", "kind", "prompt", "input", "identity",
                "capabilities", "risk", "bounds", "created_at",
                "correlation_id", "tags"
            );

            var capabilities = new java.util.LinkedHashSet<Capability>();
            for (var v : o.array("capabilities").values()) {
                capabilities.add(Capability.valueOf(Json.expectString(v, "$.capabilities[]")));
            }

            var tags = new LinkedHashMap<String, String>();
            var tagsObject = o.object("tags");
            for (var e : tagsObject.values().entrySet()) {
                tags.put(e.getKey(), Json.expectString(e.getValue(), "$.tags." + e.getKey()));
            }

            return new TaskRequest(
                o.string("task_id"),
                o.string("kind"),
                o.string("prompt"),
                o.object("input"),
                Identity.fromJson(o.object("identity")),
                capabilities,
                Risk.valueOf(o.string("risk")),
                boundsFromJson(o.object("bounds")),
                Instant.parse(o.string("created_at")),
                o.string("correlation_id"),
                tags
            );
        }
    }

    public record Evidence(
        String evidenceId,
        EvidenceKind kind,
        Instant at,
        String actor,
        Json.Obj data,
        String digest
    ) {
        public Evidence {
            evidenceId = identifier(evidenceId, "evidenceId");
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(at, "at");
            actor = bounded(actor, "actor", 1, 256);
            Objects.requireNonNull(data, "data");
            digest = hexDigest(digest, "digest");
        }

        public Json.Obj toJson() {
            return Json.obj(
                "evidence_id", evidenceId,
                "kind", kind.name(),
                "at", at.toString(),
                "actor", actor,
                "data", data,
                "digest", digest
            );
        }

        public static Evidence fromJson(Json.Obj o) {
            o.rejectUnknown("evidence_id", "kind", "at", "actor", "data", "digest");
            return new Evidence(
                o.string("evidence_id"),
                EvidenceKind.valueOf(o.string("kind")),
                Instant.parse(o.string("at")),
                o.string("actor"),
                o.object("data"),
                o.string("digest")
            );
        }
    }

    public record PolicyDecision(
        DecisionKind decision,
        String code,
        String reason,
        List<String> matchedRules,
        Set<Capability> grantedCapabilities,
        Json.Obj obligations
    ) {
        public PolicyDecision {
            Objects.requireNonNull(decision, "decision");
            code = bounded(code, "code", 1, 128);
            reason = bounded(reason, "reason", 0, 4096);
            matchedRules = List.copyOf(matchedRules);
            grantedCapabilities = Set.copyOf(grantedCapabilities);
            Objects.requireNonNull(obligations, "obligations");
        }

        public boolean allowed() { return decision == DecisionKind.ALLOW; }

        public Json.Obj toJson() {
            return Json.obj(
                "decision", decision.name(),
                "code", code,
                "reason", reason,
                "matched_rules", matchedRules,
                "granted_capabilities", grantedCapabilities.stream().map(Enum::name).sorted().toList(),
                "obligations", obligations
            );
        }
    }

    public record TaskResult(
        String taskId,
        TaskStatus status,
        Json.Value output,
        List<Evidence> evidence,
        Instant startedAt,
        Instant finishedAt,
        String errorCode,
        String errorMessage,
        int attempts
    ) {
        public TaskResult {
            taskId = identifier(taskId, "taskId");
            Objects.requireNonNull(status, "status");
            Objects.requireNonNull(output, "output");
            evidence = List.copyOf(evidence);
            Objects.requireNonNull(startedAt, "startedAt");
            Objects.requireNonNull(finishedAt, "finishedAt");
            errorCode = errorCode == null ? "" : bounded(errorCode, "errorCode", 0, 128);
            errorMessage = errorMessage == null ? "" : bounded(errorMessage, "errorMessage", 0, 8192);
            if (attempts < 0) throw new IllegalArgumentException("attempts");
        }

        public boolean success() { return status == TaskStatus.SUCCEEDED; }

        public Json.Obj toJson() {
            return Json.obj(
                "task_id", taskId,
                "status", status.name(),
                "output", output,
                "evidence", evidence.stream().map(Evidence::toJson).toList(),
                "started_at", startedAt.toString(),
                "finished_at", finishedAt.toString(),
                "error_code", errorCode,
                "error_message", errorMessage,
                "attempts", attempts
            );
        }
    }

    public record SignedEnvelope(
        String version,
        String keyId,
        String nonce,
        Instant issuedAt,
        Instant expiresAt,
        String contentType,
        Json.Obj payload,
        String signature
    ) {
        public SignedEnvelope {
            version = bounded(version, "version", 1, 32);
            keyId = identifier(keyId, "keyId");
            nonce = identifier(nonce, "nonce");
            Objects.requireNonNull(issuedAt, "issuedAt");
            Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(issuedAt)) {
                throw new IllegalArgumentException("expiresAt must follow issuedAt");
            }
            contentType = bounded(contentType, "contentType", 1, 128);
            Objects.requireNonNull(payload, "payload");
            signature = signature == null ? "" : bounded(signature, "signature", 0, 512);
        }

        public Json.Obj unsignedJson() {
            return Json.obj(
                "version", version,
                "key_id", keyId,
                "nonce", nonce,
                "issued_at", issuedAt.toString(),
                "expires_at", expiresAt.toString(),
                "content_type", contentType,
                "payload", payload
            );
        }

        public Json.Obj toJson() {
            return Json.obj(
                "version", version,
                "key_id", keyId,
                "nonce", nonce,
                "issued_at", issuedAt.toString(),
                "expires_at", expiresAt.toString(),
                "content_type", contentType,
                "payload", payload,
                "signature", signature
            );
        }

        public static SignedEnvelope fromJson(Json.Obj o) {
            o.rejectUnknown(
                "version", "key_id", "nonce", "issued_at", "expires_at",
                "content_type", "payload", "signature"
            );
            return new SignedEnvelope(
                o.string("version"),
                o.string("key_id"),
                o.string("nonce"),
                Instant.parse(o.string("issued_at")),
                Instant.parse(o.string("expires_at")),
                o.string("content_type"),
                o.object("payload"),
                o.string("signature")
            );
        }
    }

    public record Endpoint(
        URI uri,
        Duration connectTimeout,
        Duration requestTimeout,
        int maxResponseBytes
    ) {
        public Endpoint {
            Objects.requireNonNull(uri, "uri");
            Objects.requireNonNull(connectTimeout, "connectTimeout");
            Objects.requireNonNull(requestTimeout, "requestTimeout");
            if (maxResponseBytes < 1) throw new IllegalArgumentException("maxResponseBytes");
        }
    }

    private static Json.Obj boundsToJson(Bounds b) {
        return Json.obj(
            "max_prompt_chars", b.maxPromptChars(),
            "max_output_chars", b.maxOutputChars(),
            "max_evidence_items", b.maxEvidenceItems(),
            "max_attempts", b.maxAttempts(),
            "timeout_ms", b.timeout().toMillis()
        );
    }

    private static Bounds boundsFromJson(Json.Obj o) {
        o.rejectUnknown(
            "max_prompt_chars", "max_output_chars", "max_evidence_items",
            "max_attempts", "timeout_ms"
        );
        return new Bounds(
            Math.toIntExact(o.longValue("max_prompt_chars")),
            Math.toIntExact(o.longValue("max_output_chars")),
            Math.toIntExact(o.longValue("max_evidence_items")),
            Math.toIntExact(o.longValue("max_attempts")),
            Duration.ofMillis(o.longValue("timeout_ms"))
        );
    }

    static String identifier(String v, String name) {
        v = bounded(v, name, 1, 256);
        if (!v.matches("[A-Za-z0-9._:-]+")) {
            throw new IllegalArgumentException(name + " contains unsupported characters");
        }
        return v;
    }

    static String hexDigest(String v, String name) {
        v = bounded(v, name, 64, 128).toLowerCase(java.util.Locale.ROOT);
        if (!v.matches("[0-9a-f]+")) {
            throw new IllegalArgumentException(name + " must be lowercase hex");
        }
        return v;
    }

    static String bounded(String v, String name, int min, int max) {
        Objects.requireNonNull(v, name);
        if (v.length() < min || v.length() > max) {
            throw new IllegalArgumentException(
                name + " length outside [" + min + "," + max + "]"
            );
        }
        Json.validateUnicode(v);
        return v;
    }

    static Map<String, String> boundedMap(
        Map<String, String> in,
        String name,
        int maxEntries,
        int maxKey,
        int maxValue
    ) {
        Objects.requireNonNull(in, name);
        if (in.size() > maxEntries) {
            throw new IllegalArgumentException(name + " has too many entries");
        }
        var out = new LinkedHashMap<String, String>();
        for (var e : in.entrySet()) {
            out.put(
                bounded(e.getKey(), name + " key", 1, maxKey),
                bounded(e.getValue(), name + " value", 0, maxValue)
            );
        }
        return Map.copyOf(out);
    }
}
