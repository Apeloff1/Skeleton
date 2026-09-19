package com.tutolage.skeleton.controlplane;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.SplittableRandom;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/** Retry, circuit-breaker, deadline, and token-bucket primitives. */
public final class Resilience {
    private Resilience() {}

    public record RetryPolicy(
        int maxAttempts,
        Duration baseDelay,
        Duration maxDelay,
        double multiplier
    ) {
        public RetryPolicy {
            if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts");
            Objects.requireNonNull(baseDelay, "baseDelay");
            Objects.requireNonNull(maxDelay, "maxDelay");
            if (baseDelay.isNegative() || maxDelay.isNegative() || multiplier < 1) {
                throw new IllegalArgumentException("retry parameters");
            }
        }

        public Duration fullJitterDelay(int attempt, SplittableRandom random) {
            if (attempt < 1) throw new IllegalArgumentException("attempt");
            double raw = baseDelay.toMillis() * Math.pow(multiplier, attempt - 1);
            long cap = Math.min(maxDelay.toMillis(), Math.max(0, (long) raw));
            return Duration.ofMillis(cap == 0 ? 0 : random.nextLong(cap + 1));
        }

        public static RetryPolicy defaults() {
            return new RetryPolicy(3, Duration.ofMillis(100), Duration.ofSeconds(2), 2.0);
        }
    }

    public static final class Deadline {
        private final Clock clock;
        private final Instant deadline;

        public Deadline(Clock clock, Duration timeout) {
            this.clock = Objects.requireNonNull(clock, "clock");
            Objects.requireNonNull(timeout, "timeout");
            if (timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("timeout");
            this.deadline = clock.instant().plus(timeout);
        }

        public boolean expired() { return !clock.instant().isBefore(deadline); }

        public Duration remaining() {
            var d = Duration.between(clock.instant(), deadline);
            return d.isNegative() ? Duration.ZERO : d;
        }

        public Instant at() { return deadline; }

        public void throwIfExpired() {
            if (expired()) throw new DeadlineExceededException("deadline exceeded");
        }
    }

    public static final class DeadlineExceededException extends RuntimeException {
        public DeadlineExceededException(String message) { super(message); }
    }

    public enum State { CLOSED, OPEN, HALF_OPEN }

    public static final class CircuitBreaker {
        private final Clock clock;
        private final int failureThreshold;
        private final Duration openDuration;
        private final AtomicInteger failures = new AtomicInteger();
        private final AtomicLong openUntilMillis = new AtomicLong();
        private final AtomicInteger halfOpenProbe = new AtomicInteger();

        public CircuitBreaker(Clock clock, int failureThreshold, Duration openDuration) {
            this.clock = Objects.requireNonNull(clock, "clock");
            if (failureThreshold < 1) throw new IllegalArgumentException("failureThreshold");
            Objects.requireNonNull(openDuration, "openDuration");
            if (openDuration.isNegative() || openDuration.isZero()) {
                throw new IllegalArgumentException("openDuration");
            }
            this.failureThreshold = failureThreshold;
            this.openDuration = openDuration;
        }

        public State state() {
            long until = openUntilMillis.get();
            long now = clock.millis();
            if (until == 0) return State.CLOSED;
            if (now < until) return State.OPEN;
            return State.HALF_OPEN;
        }

        public boolean allowRequest() {
            var state = state();
            if (state == State.CLOSED) return true;
            if (state == State.OPEN) return false;
            return halfOpenProbe.compareAndSet(0, 1);
        }

        public void success() {
            failures.set(0);
            openUntilMillis.set(0);
            halfOpenProbe.set(0);
        }

        public void failure() {
            halfOpenProbe.set(0);
            if (failures.incrementAndGet() >= failureThreshold) {
                openUntilMillis.set(clock.millis() + openDuration.toMillis());
            }
        }
    }

    public static final class TokenBucket {
        private final Clock clock;
        private final double capacity;
        private final double refillPerSecond;
        private double tokens;
        private long lastMillis;

        public TokenBucket(Clock clock, double capacity, double refillPerSecond) {
            this.clock = Objects.requireNonNull(clock, "clock");
            if (capacity <= 0 || refillPerSecond <= 0) {
                throw new IllegalArgumentException("bucket parameters");
            }
            this.capacity = capacity;
            this.refillPerSecond = refillPerSecond;
            this.tokens = capacity;
            this.lastMillis = clock.millis();
        }

        public synchronized boolean tryAcquire(double amount) {
            if (amount <= 0 || amount > capacity) throw new IllegalArgumentException("amount");
            refill();
            if (tokens + 1e-12 < amount) return false;
            tokens -= amount;
            return true;
        }

        public synchronized double available() {
            refill();
            return tokens;
        }

        private void refill() {
            long now = clock.millis();
            long elapsed = Math.max(0, now - lastMillis);
            tokens = Math.min(
                capacity,
                tokens + (elapsed / 1000.0) * refillPerSecond
            );
            lastMillis = now;
        }
    }
}
