import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Optional Java 21 accelerator for Skeleton observability batch workloads.
 *
 * <p>This is deliberately not a second application runtime. Python remains the
 * authority for telemetry state and event emission. The JVM process accepts a
 * tiny bounded binary protocol and performs operations where primitive arrays,
 * JIT compilation, and Java 21's lightweight task scheduling are useful:</p>
 *
 * <ul>
 *   <li>histogram summaries and exact-order quantiles for large batches;</li>
 *   <li>many independent summaries in one request;</li>
 *   <li>rolling anomaly scans using O(1) window updates.</li>
 * </ul>
 *
 * <p>The source-file launcher is supported by modern Java, so Skeleton can run
 * this optional helper without adding Maven/Gradle to the Python build. Use
 * {@code java AcceleratorMain.java --stdio} for the service or
 * {@code java AcceleratorMain.java --self-test} for a local smoke test.</p>
 */
public final class AcceleratorMain {
    static final int MAGIC = 0x534B4F42; // "SKOB"
    static final short VERSION = 1;

    static final byte OP_PING = 1;
    static final byte OP_SUMMARY = 2;
    static final byte OP_MANY_SUMMARIES = 3;
    static final byte OP_ANOMALY_SCAN = 4;
    static final byte OP_SHUTDOWN = 5;

    static final byte STATUS_OK = 0;
    static final byte STATUS_BAD_REQUEST = 1;
    static final byte STATUS_INTERNAL = 2;

    static final int MAX_VALUES = 2_000_000;
    static final int MAX_SERIES = 4096;
    static final int MAX_ERROR_BYTES = 8192;
    static final int PARALLEL_SORT_THRESHOLD = 131_072;

    private AcceleratorMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--stdio".equals(args[0])) {
            runService();
            return;
        }
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }
        System.err.println("usage: java AcceleratorMain.java --stdio|--self-test");
        System.exit(64);
    }

    static void runService() throws IOException {
        var in = new DataInputStream(new BufferedInputStream(System.in, 1 << 20));
        var out = new DataOutputStream(new BufferedOutputStream(System.out, 1 << 20));
        try (var workers = Executors.newVirtualThreadPerTaskExecutor()) {
            while (true) {
                RequestHeader header;
                try {
                    header = readHeader(in);
                } catch (EOFException eof) {
                    break;
                } catch (ProtocolException malformed) {
                    System.err.println("protocol header rejected: " + sanitize(malformed.getMessage()));
                    break;
                }

                if (header.op() == OP_SHUTDOWN) {
                    writeHeader(out, header.op(), STATUS_OK, header.requestId());
                    out.flush();
                    break;
                }

                try {
                    switch (header.op()) {
                        case OP_PING -> handlePing(out, header);
                        case OP_SUMMARY -> handleSummary(in, out, header);
                        case OP_MANY_SUMMARIES -> handleManySummaries(in, out, header, workers);
                        case OP_ANOMALY_SCAN -> handleAnomalyScan(in, out, header);
                        default -> throw new ProtocolException("unsupported operation: " + header.op());
                    }
                } catch (ProtocolException | IllegalArgumentException bad) {
                    writeError(out, header, STATUS_BAD_REQUEST, bad.getMessage());
                } catch (Throwable internal) {
                    writeError(out, header, STATUS_INTERNAL, internal.getClass().getSimpleName());
                }
                out.flush();
            }
        }
    }

    static RequestHeader readHeader(DataInputStream in) throws IOException {
        int magic = in.readInt();
        if (magic != MAGIC) throw new ProtocolException("invalid magic");
        short version = in.readShort();
        if (version != VERSION) throw new ProtocolException("unsupported protocol version");
        byte op = in.readByte();
        long requestId = in.readLong();
        if (requestId <= 0) throw new ProtocolException("request id must be positive");
        return new RequestHeader(op, requestId);
    }

    static void writeHeader(DataOutputStream out, byte op, byte status, long requestId) throws IOException {
        out.writeInt(MAGIC);
        out.writeShort(VERSION);
        out.writeByte(op);
        out.writeByte(status);
        out.writeLong(requestId);
    }

    static void handlePing(DataOutputStream out, RequestHeader header) throws IOException {
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeLong(System.nanoTime());
        out.writeInt(Runtime.getRuntime().availableProcessors());
    }

    static void handleSummary(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        double[] values = readValues(in, MAX_VALUES);
        if (values.length == 0) throw new ProtocolException("summary requires at least one value");
        Summary summary = Summary.of(values);
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        summary.writeTo(out);
    }

    static void handleManySummaries(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header,
        ExecutorService workers
    ) throws IOException {
        int seriesCount = readBoundedCount(in, "series count", 1, MAX_SERIES);
        var series = new ArrayList<double[]>(seriesCount);
        long total = 0;
        for (int i = 0; i < seriesCount; i++) {
            double[] values = readValues(in, MAX_VALUES);
            if (values.length == 0) throw new ProtocolException("summary series cannot be empty");
            total += values.length;
            if (total > MAX_VALUES) {
                throw new ProtocolException("aggregate value bound exceeded");
            }
            series.add(values);
        }

        List<Summary> summaries;
        if (seriesCount == 1) {
            summaries = List.of(Summary.of(series.get(0)));
        } else {
            var tasks = new ArrayList<Callable<Summary>>(seriesCount);
            for (double[] values : series) {
                tasks.add(() -> Summary.of(values));
            }
            try {
                var futures = workers.invokeAll(tasks);
                summaries = new ArrayList<>(seriesCount);
                for (var future : futures) {
                    summaries.add(future.get());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException("summary batch interrupted", interrupted);
            } catch (ExecutionException failed) {
                throw new IOException("summary worker failed", failed.getCause());
            }
        }

        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(summaries.size());
        for (Summary summary : summaries) summary.writeTo(out);
    }

    static void handleAnomalyScan(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int windowSize = readBoundedCount(in, "window size", 10, MAX_VALUES);
        double threshold = readFinite(in, "threshold");
        if (!(threshold > 0.0) || threshold > 1000.0) {
            throw new ProtocolException("threshold must be in (0, 1000]");
        }

        double[] history = readValues(in, windowSize);
        double[] incoming = readValues(in, MAX_VALUES);
        var window = new RollingWindow(windowSize);
        int historyStart = Math.max(0, history.length - windowSize);
        for (int i = historyStart; i < history.length; i++) window.add(history[i]);

        var rows = new AnomalyRow[incoming.length];
        for (int i = 0; i < incoming.length; i++) {
            double value = incoming[i];
            boolean ready = window.size() >= 10;
            double mean = ready ? window.mean() : 0.0;
            double stdev = ready ? window.sampleStdDev() : 0.0;
            boolean anomaly = ready && stdev > 0.0 && Math.abs(value - mean) > threshold * stdev;
            rows[i] = new AnomalyRow(ready, anomaly, mean, stdev);
            window.add(value);
        }

        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(rows.length);
        for (AnomalyRow row : rows) row.writeTo(out);
    }

    static double[] readValues(DataInputStream in, int max) throws IOException {
        int count = readBoundedCount(in, "value count", 0, max);
        var values = new double[count];
        for (int i = 0; i < count; i++) values[i] = readFinite(in, "value");
        return values;
    }

    static int readBoundedCount(DataInputStream in, String name, int min, int max) throws IOException {
        int value = in.readInt();
        if (value < min || value > max) {
            throw new ProtocolException(name + " outside [" + min + ", " + max + "]");
        }
        return value;
    }

    static double readFinite(DataInputStream in, String name) throws IOException {
        double value = in.readDouble();
        if (!Double.isFinite(value)) throw new ProtocolException(name + " must be finite");
        return value;
    }

    static void writeError(
        DataOutputStream out,
        RequestHeader header,
        byte status,
        String message
    ) throws IOException {
        writeHeader(out, header.op(), status, header.requestId());
        byte[] bytes = sanitize(message).getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_ERROR_BYTES) bytes = Arrays.copyOf(bytes, MAX_ERROR_BYTES);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String sanitize(String message) {
        if (message == null || message.isBlank()) return "accelerator error";
        StringBuilder result = new StringBuilder(Math.min(message.length(), 512));
        for (int i = 0; i < message.length() && result.length() < 512; i++) {
            char c = message.charAt(i);
            if (c >= 0x20 && c != 0x7f) result.append(c);
        }
        return result.isEmpty() ? "accelerator error" : result.toString();
    }

    record RequestHeader(byte op, long requestId) {}

    record Summary(
        long count,
        double min,
        double max,
        double mean,
        double sampleVariance,
        double sampleStdDev,
        double p50,
        double p90,
        double p95,
        double p99,
        double sum
    ) {
        static Summary of(double[] input) {
            if (input.length == 0) {
                throw new IllegalArgumentException("summary requires at least one value");
            }

            var moments = Moments.of(input);
            double[] sorted = input.clone();
            if (sorted.length >= PARALLEL_SORT_THRESHOLD) Arrays.parallelSort(sorted);
            else Arrays.sort(sorted);

            double p50;
            int mid = sorted.length / 2;
            if ((sorted.length & 1) == 0) p50 = (sorted[mid - 1] + sorted[mid]) / 2.0;
            else p50 = sorted[mid];

            return new Summary(
                sorted.length,
                sorted[0],
                sorted[sorted.length - 1],
                moments.mean(),
                moments.sampleVariance(),
                Math.sqrt(moments.sampleVariance()),
                p50,
                percentileIndex(sorted, 0.90),
                percentileIndex(sorted, 0.95),
                percentileIndex(sorted, 0.99),
                moments.sum()
            );
        }

        static double percentileIndex(double[] sorted, double q) {
            if (sorted.length == 1) return sorted[0];
            int index = (int) Math.floor(sorted.length * q);
            if (index >= sorted.length) index = sorted.length - 1;
            return sorted[index];
        }

        void writeTo(DataOutputStream out) throws IOException {
            out.writeLong(count);
            out.writeDouble(min);
            out.writeDouble(max);
            out.writeDouble(mean);
            out.writeDouble(sampleVariance);
            out.writeDouble(sampleStdDev);
            out.writeDouble(p50);
            out.writeDouble(p90);
            out.writeDouble(p95);
            out.writeDouble(p99);
            out.writeDouble(sum);
        }
    }

    record Moments(double mean, double sampleVariance, double sum) {
        static Moments of(double[] values) {
            if (values.length == 0) throw new IllegalArgumentException("empty values");

            long n = 0;
            double mean = 0.0;
            double m2 = 0.0;
            double sum = 0.0;
            double correction = 0.0;

            for (double x : values) {
                if (!Double.isFinite(x)) throw new IllegalArgumentException("non-finite input");
                n++;
                double delta = x - mean;
                mean += delta / n;
                double delta2 = x - mean;
                m2 += delta * delta2;

                double t = sum + x;
                if (Math.abs(sum) >= Math.abs(x)) correction += (sum - t) + x;
                else correction += (x - t) + sum;
                sum = t;
            }

            double variance = n > 1 ? m2 / (n - 1) : 0.0;
            if (variance < 0.0 && variance > -1e-15) variance = 0.0;
            return new Moments(mean, variance, sum + correction);
        }
    }

    static final class RollingWindow {
        private final double[] ring;
        private int start;
        private int size;
        private long updates;
        private double sum;
        private double sumSq;

        RollingWindow(int capacity) {
            if (capacity < 1) throw new IllegalArgumentException("capacity");
            this.ring = new double[capacity];
        }

        int size() { return size; }

        void add(double value) {
            if (!Double.isFinite(value)) throw new IllegalArgumentException("non-finite value");
            if (size < ring.length) {
                int index = (start + size) % ring.length;
                ring[index] = value;
                size++;
                sum += value;
                sumSq += value * value;
            } else {
                double evicted = ring[start];
                sum -= evicted;
                sumSq -= evicted * evicted;
                ring[start] = value;
                start = (start + 1) % ring.length;
                sum += value;
                sumSq += value * value;
            }
            updates++;
            if ((updates & 1023) == 0) rebase();
        }

        double mean() {
            if (size == 0) return Double.NaN;
            return sum / size;
        }

        double sampleStdDev() {
            if (size < 2) return 0.0;
            double centered = sumSq - (sum * sum / size);
            double tolerance = Math.max(1.0, Math.abs(sumSq)) * 1e-14;
            if (centered < 0.0 && centered >= -tolerance) centered = 0.0;
            if (centered < 0.0) return welfordStdDev();
            return Math.sqrt(centered / (size - 1));
        }

        private double welfordStdDev() {
            if (size < 2) return 0.0;
            long n = 0;
            double mean = 0.0;
            double m2 = 0.0;
            for (int i = 0; i < size; i++) {
                double x = ring[(start + i) % ring.length];
                n++;
                double delta = x - mean;
                mean += delta / n;
                m2 += delta * (x - mean);
            }
            return Math.sqrt(Math.max(0.0, m2 / (n - 1)));
        }

        private void rebase() {
            double newSum = 0.0;
            double newSumSq = 0.0;
            double sumComp = 0.0;
            double sqComp = 0.0;
            for (int i = 0; i < size; i++) {
                double x = ring[(start + i) % ring.length];
                double y = x - sumComp;
                double t = newSum + y;
                sumComp = (t - newSum) - y;
                newSum = t;

                double square = x * x;
                double sy = square - sqComp;
                double st = newSumSq + sy;
                sqComp = (st - newSumSq) - sy;
                newSumSq = st;
            }
            sum = newSum;
            sumSq = newSumSq;
        }
    }

    record AnomalyRow(boolean ready, boolean anomaly, double mean, double stdev) {
        void writeTo(DataOutputStream out) throws IOException {
            out.writeBoolean(ready);
            out.writeBoolean(anomaly);
            out.writeDouble(mean);
            out.writeDouble(stdev);
        }
    }

    static final class ProtocolException extends IOException {
        ProtocolException(String message) { super(message); }
    }

    static void selfTest() throws Exception {
        var values = new double[100];
        for (int i = 0; i < values.length; i++) values[i] = i + 1;
        var summary = Summary.of(values);
        check(summary.count() == 100, "count");
        check(close(summary.min(), 1.0), "min");
        check(close(summary.max(), 100.0), "max");
        check(close(summary.mean(), 50.5), "mean");
        check(close(summary.p50(), 50.5), "p50");
        check(close(summary.p99(), 100.0), "p99");

        var window = new RollingWindow(100);
        for (int i = 0; i < 20; i++) window.add(10.0 + (i % 3));
        check(window.size() == 20, "rolling size");
        check(window.sampleStdDev() > 0.0, "rolling stdev");
        double mean = window.mean();
        double stdev = window.sampleStdDev();
        check(Math.abs(1000.0 - mean) > 3.0 * stdev, "outlier detection");

        try (var workers = Executors.newVirtualThreadPerTaskExecutor()) {
            var tasks = new ArrayList<Callable<Summary>>();
            for (int i = 0; i < 64; i++) {
                final int offset = i;
                tasks.add(() -> Summary.of(new double[] {offset, offset + 1.0, offset + 2.0}));
            }
            var futures = workers.invokeAll(tasks);
            for (int i = 0; i < futures.size(); i++) {
                check(close(futures.get(i).get().mean(), i + 1.0), "virtual-thread batch " + i);
            }
        }

        System.out.println("AcceleratorMain self-test: OK");
    }

    static boolean close(double a, double b) {
        return Math.abs(a - b) <= 1e-12 * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
    }

    static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError("self-test failed: " + name);
    }
}
