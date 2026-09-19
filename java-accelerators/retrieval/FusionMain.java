import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.PriorityQueue;

/**
 * Optional numeric aggregation kernel for Skeleton retrieval fusion.
 *
 * <p>Python owns retrieval planes, fragment identity, score policy, RRF
 * constants, plane weights, and result construction. This helper receives only
 * bounded (fragmentIndex, contribution) pairs and returns stable top-K aggregate
 * scores.</p>
 */
public final class FusionMain {
    static final int MAGIC = 0x534B5246; // "SKRF"
    static final short VERSION = 1;

    static final byte OP_PING = 1;
    static final byte OP_AGGREGATE_TOP_K = 2;
    static final byte OP_SHUTDOWN = 3;

    static final byte STATUS_OK = 0;
    static final byte STATUS_BAD_REQUEST = 1;
    static final byte STATUS_INTERNAL = 2;

    static final int MAX_FRAGMENTS = 200_000;
    static final int MAX_CONTRIBUTIONS = 2_000_000;
    static final int MAX_ERROR_BYTES = 8192;

    private FusionMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--stdio".equals(args[0])) {
            runService();
            return;
        }
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }
        System.err.println("usage: java FusionMain.java --stdio|--self-test");
        System.exit(64);
    }

    static void runService() throws IOException {
        var in = new DataInputStream(new BufferedInputStream(System.in, 1 << 20));
        var out = new DataOutputStream(new BufferedOutputStream(System.out, 1 << 20));

        while (true) {
            RequestHeader header;
            try {
                header = readHeader(in);
            } catch (EOFException eof) {
                break;
            } catch (ProtocolException malformed) {
                System.err.println(
                    "protocol header rejected: " + sanitize(malformed.getMessage())
                );
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
                    case OP_AGGREGATE_TOP_K -> handleAggregateTopK(in, out, header);
                    default -> throw new ProtocolException(
                        "unsupported operation: " + header.op()
                    );
                }
            } catch (ProtocolException | IllegalArgumentException bad) {
                writeError(out, header, STATUS_BAD_REQUEST, bad.getMessage());
            } catch (Throwable internal) {
                writeError(
                    out,
                    header,
                    STATUS_INTERNAL,
                    internal.getClass().getSimpleName()
                );
            }
            out.flush();
        }
    }

    static RequestHeader readHeader(DataInputStream in) throws IOException {
        int magic = in.readInt();
        if (magic != MAGIC) throw new ProtocolException("invalid magic");
        short version = in.readShort();
        if (version != VERSION) {
            throw new ProtocolException("unsupported protocol version");
        }
        byte op = in.readByte();
        long requestId = in.readLong();
        if (requestId <= 0) {
            throw new ProtocolException("request id must be positive");
        }
        return new RequestHeader(op, requestId);
    }

    static void writeHeader(
        DataOutputStream out,
        byte op,
        byte status,
        long requestId
    ) throws IOException {
        out.writeInt(MAGIC);
        out.writeShort(VERSION);
        out.writeByte(op);
        out.writeByte(status);
        out.writeLong(requestId);
    }

    static void handlePing(
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeLong(System.nanoTime());
        out.writeInt(Runtime.getRuntime().availableProcessors());
    }

    static void handleAggregateTopK(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int fragmentCount = readBoundedInt(
            in,
            "fragment count",
            1,
            MAX_FRAGMENTS
        );
        int contributionCount = readBoundedInt(
            in,
            "contribution count",
            1,
            MAX_CONTRIBUTIONS
        );
        int topK = readBoundedInt(in, "top_k", 1, fragmentCount);

        var contributions = new Contribution[contributionCount];
        for (int index = 0; index < contributionCount; index++) {
            int fragmentIndex = readBoundedInt(
                in,
                "fragment index",
                0,
                fragmentCount - 1
            );
            double value = readFinite(in, "contribution");
            contributions[index] = new Contribution(fragmentIndex, value);
        }

        List<Hit> hits = aggregateTopK(fragmentCount, contributions, topK);
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(hits.size());
        for (Hit hit : hits) {
            out.writeInt(hit.index());
            out.writeDouble(hit.score());
        }
    }

    static List<Hit> aggregateTopK(
        int fragmentCount,
        Contribution[] contributions,
        int topK
    ) {
        if (fragmentCount < 1 || fragmentCount > MAX_FRAGMENTS) {
            throw new IllegalArgumentException("fragment count");
        }
        if (
            contributions == null
            || contributions.length < 1
            || contributions.length > MAX_CONTRIBUTIONS
        ) {
            throw new IllegalArgumentException("contribution count");
        }
        if (topK < 1 || topK > fragmentCount) {
            throw new IllegalArgumentException("topK");
        }

        double[] scores = new double[fragmentCount];
        boolean[] seen = new boolean[fragmentCount];
        for (Contribution contribution : contributions) {
            if (contribution == null) {
                throw new IllegalArgumentException("null contribution");
            }
            int index = contribution.index();
            double value = contribution.value();
            if (index < 0 || index >= fragmentCount) {
                throw new IllegalArgumentException("fragment index");
            }
            if (!Double.isFinite(value)) {
                throw new IllegalArgumentException("non-finite contribution");
            }
            double next = scores[index] + value;
            if (!Double.isFinite(next)) {
                throw new IllegalArgumentException("non-finite aggregate score");
            }
            scores[index] = next;
            seen[index] = true;
        }

        var heap = new PriorityQueue<Hit>(
            Math.min(topK, 1024),
            Comparator
                .comparingDouble(Hit::score)
                .thenComparing(Comparator.comparingInt(Hit::index).reversed())
        );

        for (int index = 0; index < fragmentCount; index++) {
            if (!seen[index]) {
                throw new IllegalArgumentException(
                    "fragment without contribution: " + index
                );
            }
            Hit hit = new Hit(index, scores[index]);
            if (heap.size() < topK) {
                heap.add(hit);
            } else if (isBetter(hit, heap.peek())) {
                heap.poll();
                heap.add(hit);
            }
        }

        var ordered = new ArrayList<>(heap);
        ordered.sort(
            Comparator
                .comparingDouble(Hit::score)
                .reversed()
                .thenComparingInt(Hit::index)
        );
        return ordered;
    }

    static boolean isBetter(Hit candidate, Hit currentWorst) {
        int score = Double.compare(candidate.score(), currentWorst.score());
        if (score != 0) return score > 0;
        return candidate.index() < currentWorst.index();
    }

    static int readBoundedInt(
        DataInputStream in,
        String name,
        int min,
        int max
    ) throws IOException {
        int value = in.readInt();
        if (value < min || value > max) {
            throw new ProtocolException(
                name + " outside [" + min + ", " + max + "]"
            );
        }
        return value;
    }

    static double readFinite(
        DataInputStream in,
        String name
    ) throws IOException {
        double value = in.readDouble();
        if (!Double.isFinite(value)) {
            throw new ProtocolException(name + " must be finite");
        }
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
        if (bytes.length > MAX_ERROR_BYTES) {
            bytes = java.util.Arrays.copyOf(bytes, MAX_ERROR_BYTES);
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String sanitize(String message) {
        if (message == null || message.isBlank()) {
            return "retrieval fusion accelerator error";
        }
        StringBuilder result = new StringBuilder(
            Math.min(message.length(), 512)
        );
        for (int i = 0; i < message.length() && result.length() < 512; i++) {
            char c = message.charAt(i);
            if (c >= 0x20 && c != 0x7f) result.append(c);
        }
        return result.isEmpty()
            ? "retrieval fusion accelerator error"
            : result.toString();
    }

    record RequestHeader(byte op, long requestId) {}

    record Contribution(int index, double value) {}

    record Hit(int index, double score) {}

    static final class ProtocolException extends IOException {
        ProtocolException(String message) {
            super(message);
        }
    }

    static void selfTest() {
        Contribution[] contributions = {
            new Contribution(0, 1.0),
            new Contribution(1, 0.5),
            new Contribution(2, 0.75),
            new Contribution(0, 0.25),
            new Contribution(1, 0.75),
            new Contribution(2, 0.5),
            new Contribution(3, -0.25),
        };

        List<Hit> hits = aggregateTopK(4, contributions, 3);
        check(hits.size() == 3, "hit count");
        check(hits.get(0).index() == 0, "stable first tie");
        check(hits.get(1).index() == 1, "stable second tie");
        check(hits.get(2).index() == 2, "stable third tie");
        check(close(hits.get(0).score(), 1.25), "aggregate score 0");
        check(close(hits.get(1).score(), 1.25), "aggregate score 1");
        check(close(hits.get(2).score(), 1.25), "aggregate score 2");

        boolean missingRaised = false;
        try {
            aggregateTopK(
                2,
                new Contribution[] {new Contribution(0, 1.0)},
                1
            );
        } catch (IllegalArgumentException expected) {
            missingRaised = true;
        }
        check(missingRaised, "missing fragment contribution");

        boolean boundRaised = false;
        try {
            aggregateTopK(1, contributions, 2);
        } catch (IllegalArgumentException expected) {
            boundRaised = true;
        }
        check(boundRaised, "top-k bound");

        System.out.println("FusionMain self-test: OK");
    }

    static boolean close(double a, double b) {
        return Math.abs(a - b)
            <= 1e-12 * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
    }

    static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError("self-test failed: " + name);
        }
    }
}
