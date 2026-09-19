package com.tutolage.skeleton.controlplane;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.InetAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/** Security primitives for signed protocol messages, replay defense, and egress validation. */
public final class Security {
    private Security() {}

    public static byte[] sha256(byte[] bytes) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(bytes);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static String sha256Hex(byte[] bytes) { return hex(sha256(bytes)); }

    public static String sha256Hex(String text) {
        return sha256Hex(text.getBytes(StandardCharsets.UTF_8));
    }

    public static String hex(byte[] bytes) {
        var out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) out.append(String.format("%02x", b & 0xff));
        return out.toString();
    }

    public static String base64Url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static byte[] hmacSha256(byte[] key, byte[] data) {
        try {
            var mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static boolean constantTimeEquals(String a, String b) {
        if (a == null || b == null) return false;
        return MessageDigest.isEqual(
            a.getBytes(StandardCharsets.US_ASCII),
            b.getBytes(StandardCharsets.US_ASCII)
        );
    }

    public record SecretKey(
        String keyId,
        byte[] key,
        Instant notBefore,
        Instant notAfter
    ) {
        public SecretKey {
            keyId = Contracts.identifier(keyId, "keyId");
            key = key.clone();
            if (key.length < 32) throw new IllegalArgumentException("HMAC key must be >= 256 bits");
            Objects.requireNonNull(notBefore, "notBefore");
            Objects.requireNonNull(notAfter, "notAfter");
            if (!notAfter.isAfter(notBefore)) {
                throw new IllegalArgumentException("invalid key validity interval");
            }
        }

        @Override
        public byte[] key() { return key.clone(); }

        public boolean activeAt(Instant instant) {
            return !instant.isBefore(notBefore) && instant.isBefore(notAfter);
        }
    }

    public static final class KeyRing {
        private final Map<String, SecretKey> keys;

        public KeyRing(Iterable<SecretKey> keys) {
            var map = new LinkedHashMap<String, SecretKey>();
            for (var key : keys) {
                if (map.put(key.keyId(), key) != null) {
                    throw new IllegalArgumentException("duplicate key id: " + key.keyId());
                }
            }
            if (map.isEmpty()) throw new IllegalArgumentException("empty key ring");
            this.keys = Map.copyOf(map);
        }

        public SecretKey require(String id, Instant at) {
            var key = keys.get(id);
            if (key == null) throw new SecurityException("unknown key id");
            if (!key.activeAt(at)) throw new SecurityException("key outside validity interval");
            return key;
        }

        public Set<String> keyIds() { return keys.keySet(); }
    }

    public static final class EnvelopeSigner {
        private final KeyRing keyRing;
        private final Clock clock;
        private final SecureRandom random;

        public EnvelopeSigner(KeyRing keyRing, Clock clock, SecureRandom random) {
            this.keyRing = Objects.requireNonNull(keyRing, "keyRing");
            this.clock = Objects.requireNonNull(clock, "clock");
            this.random = Objects.requireNonNull(random, "random");
        }

        public Contracts.SignedEnvelope sign(
            String keyId,
            String contentType,
            Json.Obj payload,
            Duration ttl
        ) {
            if (ttl.isNegative() || ttl.isZero()) throw new IllegalArgumentException("ttl");
            var now = clock.instant();
            var nonceBytes = new byte[24];
            random.nextBytes(nonceBytes);

            var unsigned = new Contracts.SignedEnvelope(
                "1",
                keyId,
                base64Url(nonceBytes),
                now,
                now.plus(ttl),
                contentType,
                payload,
                ""
            );

            var key = keyRing.require(keyId, now);
            var signature = base64Url(
                hmacSha256(key.key(), unsigned.unsignedJson().canonicalUtf8())
            );

            return new Contracts.SignedEnvelope(
                unsigned.version(),
                unsigned.keyId(),
                unsigned.nonce(),
                unsigned.issuedAt(),
                unsigned.expiresAt(),
                unsigned.contentType(),
                unsigned.payload(),
                signature
            );
        }

        public void verify(
            Contracts.SignedEnvelope envelope,
            Duration allowedClockSkew,
            Duration maxTtl
        ) {
            var now = clock.instant();
            if (envelope.issuedAt().isAfter(now.plus(allowedClockSkew))) {
                throw new SecurityException("envelope issued in the future");
            }
            if (envelope.expiresAt().isBefore(now.minus(allowedClockSkew))) {
                throw new SecurityException("envelope expired");
            }
            if (Duration.between(envelope.issuedAt(), envelope.expiresAt()).compareTo(maxTtl) > 0) {
                throw new SecurityException("envelope ttl exceeds maximum");
            }

            var key = keyRing.require(envelope.keyId(), envelope.issuedAt());
            var expected = base64Url(
                hmacSha256(key.key(), envelope.unsignedJson().canonicalUtf8())
            );
            if (!constantTimeEquals(expected, envelope.signature())) {
                throw new SecurityException("invalid envelope signature");
            }
        }
    }

    public static final class ReplayGuard {
        private final Clock clock;
        private final Duration retention;
        private final int maxEntries;
        private final ConcurrentHashMap<String, Instant> seen = new ConcurrentHashMap<>();
        private final ArrayDeque<Entry> order = new ArrayDeque<>();
        private final Object lock = new Object();

        private record Entry(String nonce, Instant expires) {}

        public ReplayGuard(Clock clock, Duration retention, int maxEntries) {
            this.clock = Objects.requireNonNull(clock, "clock");
            this.retention = Objects.requireNonNull(retention, "retention");
            if (retention.isNegative() || retention.isZero()) {
                throw new IllegalArgumentException("retention");
            }
            if (maxEntries < 1) throw new IllegalArgumentException("maxEntries");
            this.maxEntries = maxEntries;
        }

        public void acceptOnce(String nonce) {
            Contracts.identifier(nonce, "nonce");
            var now = clock.instant();
            var expires = now.plus(retention);

            synchronized (lock) {
                purge(now);
                if (seen.putIfAbsent(nonce, expires) != null) {
                    throw new SecurityException("replayed nonce");
                }
                order.addLast(new Entry(nonce, expires));

                while (order.size() > maxEntries) {
                    var evicted = order.removeFirst();
                    seen.remove(evicted.nonce(), evicted.expires());
                }
            }
        }

        public int size() {
            synchronized (lock) {
                purge(clock.instant());
                return seen.size();
            }
        }

        private void purge(Instant now) {
            while (!order.isEmpty() && !order.peekFirst().expires().isAfter(now)) {
                var entry = order.removeFirst();
                seen.remove(entry.nonce(), entry.expires());
            }
        }
    }

    public record EgressPolicy(
        Set<String> allowedSchemes,
        Set<String> allowedHosts,
        boolean allowPrivateAddresses,
        Set<Integer> allowedPorts
    ) {
        public EgressPolicy {
            allowedSchemes = normalize(allowedSchemes);
            allowedHosts = normalize(allowedHosts);
            allowedPorts = Set.copyOf(allowedPorts);
            if (allowedSchemes.isEmpty()) throw new IllegalArgumentException("allowedSchemes");
        }

        private static Set<String> normalize(Set<String> input) {
            return input.stream()
                .map(x -> x.toLowerCase(java.util.Locale.ROOT))
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        }

        public URI validate(URI uri) {
            Objects.requireNonNull(uri, "uri");
            String scheme = lower(uri.getScheme());
            String host = lower(uri.getHost());

            if (scheme == null || !allowedSchemes.contains(scheme)) {
                throw new SecurityException("scheme denied");
            }
            if (host == null || host.isBlank()) throw new SecurityException("host required");
            if (uri.getUserInfo() != null) throw new SecurityException("userinfo denied");
            if (uri.getFragment() != null) throw new SecurityException("fragment denied");

            if (!allowedHosts.isEmpty() && !allowedHosts.contains(host)) {
                throw new SecurityException("host denied: " + host);
            }

            int port = uri.getPort();
            if (port < 0) port = scheme.equals("https") ? 443 : 80;
            if (!allowedPorts.isEmpty() && !allowedPorts.contains(port)) {
                throw new SecurityException("port denied: " + port);
            }

            if (!allowPrivateAddresses) {
                try {
                    for (var address : InetAddress.getAllByName(host)) {
                        if (isPrivate(address)) {
                            throw new SecurityException(
                                "private/reserved address denied: " + address.getHostAddress()
                            );
                        }
                    }
                } catch (SecurityException e) {
                    throw e;
                } catch (Exception e) {
                    throw new SecurityException("DNS resolution failed", e);
                }
            }

            return uri;
        }

        private static String lower(String s) {
            return s == null ? null : s.toLowerCase(java.util.Locale.ROOT);
        }

        private static boolean isPrivate(InetAddress address) {
            return address.isAnyLocalAddress()
                || address.isLoopbackAddress()
                || address.isLinkLocalAddress()
                || address.isSiteLocalAddress()
                || address.isMulticastAddress();
        }
    }

    public static String randomToken(SecureRandom random, int bytes) {
        if (bytes < 16) throw new IllegalArgumentException("minimum 128 bits");
        var b = new byte[bytes];
        random.nextBytes(b);
        return base64Url(b);
    }
}
