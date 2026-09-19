import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Optional dense-vector top-K accelerator for Skeleton's Python VectorStore.
 *
 * <p>Python owns embeddings, metadata filtering, document identity, and result
 * construction. This helper only receives one query vector plus a bounded batch
 * of candidate vectors and returns stable cosine-similarity top-K indices.</p>
 */
public final class VectorSearchMain {
    static final int MAGIC = 0x534B5653; // "SKVS"
    static final short VERSION = 1;

    static final byte OP_PING = 1;
    static final byte OP_TOP_K = 2;
    static final byte OP_SHUTDOWN = 3;
    static final byte OP_BATCH_TOP_K = 4;

    static final byte STATUS_OK = 0;
    static final byte STATUS_BAD_REQUEST = 1;
    static final byte STATUS_INTERNAL = 2;

    static final int MAX_DIMENSIONS = 4096;
    static final int MAX_CANDIDATES = 100_000;
    static final int MAX_QUERIES = 512;
    static final long MAX_ELEMENTS = 4_000_000L;
    static final int MAX_ERROR_BYTES = 8192;
    static final int MAX_CPU_WORKERS = 32;

    private VectorSearchMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--stdio".equals(args[0])) {
            runService();
            return;
        }
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }
        System.err.println("usage: java VectorSearchMain.java --stdio|--self-test");
        System.exit(64);
    }

    static void runService() throws IOException {
        var in = new DataInputStream(new BufferedInputStream(System.in, 1 << 20));
        var out = new DataOutputStream(new BufferedOutputStream(System.out, 1 << 20));
        int workerCount = Math.max(
            1,
            Math.min(MAX_CPU_WORKERS, Runtime.getRuntime().availableProcessors())
        );

        try (var workers = Executors.newFixedThreadPool(workerCount)) {
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
                        case OP_TOP_K -> handleTopK(in, out, header);
                        case OP_BATCH_TOP_K -> handleBatchTopK(in, out, header, workers);
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

    static void handlePing(DataOutputStream out, RequestHeader header) throws IOException {
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeLong(System.nanoTime());
        out.writeInt(Runtime.getRuntime().availableProcessors());
    }

    static void handleTopK(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int dimensions = readBoundedInt(in, "dimensions", 1, MAX_DIMENSIONS);
        int candidates = readBoundedInt(in, "candidate count", 1, MAX_CANDIDATES);
        int topK = readBoundedInt(in, "top_k", 1, candidates);
        long elements = (long) dimensions * candidates;
        if (elements > MAX_ELEMENTS) {
            throw new ProtocolException("vector element bound exceeded");
        }

        double queryNorm = readPositiveFinite(in, "query norm");
        double[] query = new double[dimensions];
        for (int d = 0; d < dimensions; d++) {
            query[d] = readFinite(in, "query component");
        }

        var heap = new PriorityQueue<Hit>(
            Math.min(topK, 1024),
            Comparator
                .comparingDouble(Hit::similarity)
                .thenComparing(Comparator.comparingInt(Hit::index).reversed())
        );

        for (int index = 0; index < candidates; index++) {
            double candidateNorm = readPositiveFinite(in, "candidate norm");
            double dot = 0.0;
            for (int d = 0; d < dimensions; d++) {
                double value = readFinite(in, "candidate component");
                dot += query[d] * value;
            }

            double similarity = dot / (queryNorm * candidateNorm);
            if (!Double.isFinite(similarity)) {
                throw new ProtocolException("non-finite cosine similarity");
            }
            if (similarity > 1.0 && similarity < 1.0 + 1e-12) similarity = 1.0;
            if (similarity < -1.0 && similarity > -1.0 - 1e-12) similarity = -1.0;

            var hit = new Hit(index, similarity);
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
                .comparingDouble(Hit::similarity)
                .reversed()
                .thenComparingInt(Hit::index)
        );

        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(ordered.size());
        for (var hit : ordered) {
            out.writeInt(hit.index());
            out.writeDouble(hit.similarity());
        }
    }

    static void handleBatchTopK(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header,
        ExecutorService workers
    ) throws IOException {
        int dimensions = readBoundedInt(in, "dimensions", 1, MAX_DIMENSIONS);
        int queryCount = readBoundedInt(in, "query count", 1, MAX_QUERIES);
        int candidates = readBoundedInt(in, "candidate count", 1, MAX_CANDIDATES);
        int topK = readBoundedInt(in, "top_k", 1, candidates);
        long elements = (long) dimensions * ((long) queryCount + candidates);
        if (elements > MAX_ELEMENTS) {
            throw new ProtocolException("vector element bound exceeded");
        }

        double[] queryNorms = new double[queryCount];
        double[][] queries = new double[queryCount][dimensions];
        for (int q = 0; q < queryCount; q++) {
            queryNorms[q] = readPositiveFinite(in, "query norm");
            for (int d = 0; d < dimensions; d++) {
                queries[q][d] = readFinite(in, "query component");
            }
        }

        double[] candidateNorms = new double[candidates];
        var vectors = new ArrayList<double[]>(candidates);
        for (int index = 0; index < candidates; index++) {
            candidateNorms[index] = readPositiveFinite(in, "candidate norm");
            double[] vector = new double[dimensions];
            for (int d = 0; d < dimensions; d++) {
                vector[d] = readFinite(in, "candidate component");
            }
            vectors.add(vector);
        }

        var tasks = new ArrayList<Callable<List<Hit>>>(queryCount);
        for (int q = 0; q < queryCount; q++) {
            final double[] query = queries[q];
            final double queryNorm = queryNorms[q];
            tasks.add(() -> topKForTest(query, queryNorm, vectors, candidateNorms, topK));
        }

        List<List<Hit>> results = new ArrayList<>(queryCount);
        try {
            var futures = workers.invokeAll(tasks);
            for (var future : futures) {
                results.add(future.get());
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("batch vector scoring interrupted", interrupted);
        } catch (ExecutionException failed) {
            throw new IOException("batch vector scoring failed", failed.getCause());
        }

        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(results.size());
        for (var hits : results) {
            out.writeInt(hits.size());
            for (var hit : hits) {
                out.writeInt(hit.index());
                out.writeDouble(hit.similarity());
            }
        }
    }

    static List<Hit> topKFlat(
        double[] queryMatrix,
        int queryOffset,
        double queryNorm,
        double[] candidateMatrix,
        double[] candidateNorms,
        int dimensions,
        int candidateCount,
        int topK
    ) {
        var heap = new PriorityQueue<Hit>(
            Math.min(topK, 1024),
            Comparator
                .comparingDouble(Hit::similarity)
                .thenComparing(Comparator.comparingInt(Hit::index).reversed())
        );

        for (int candidateIndex = 0; candidateIndex < candidateCount; candidateIndex++) {
            int candidateOffset = candidateIndex * dimensions;
            double dot = 0.0;
            for (int d = 0; d < dimensions; d++) {
                dot += queryMatrix[queryOffset + d] * candidateMatrix[candidateOffset + d];
            }
            double similarity = dot / (queryNorm * candidateNorms[candidateIndex]);
            if (!Double.isFinite(similarity)) {
                throw new IllegalArgumentException("non-finite cosine similarity");
            }
            if (similarity > 1.0 && similarity < 1.0 + 1e-12) similarity = 1.0;
            if (similarity < -1.0 && similarity > -1.0 - 1e-12) similarity = -1.0;

            var hit = new Hit(candidateIndex, similarity);
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
                .comparingDouble(Hit::similarity)
                .reversed()
                .thenComparingInt(Hit::index)
        );
        return ordered;
    }

    static boolean isBetter(Hit candidate, Hit currentWorst) {
        int score = Double.compare(candidate.similarity(), currentWorst.similarity());
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
            throw new ProtocolException(name + " outside [" + min + ", " + max + "]");
        }
        return value;
    }

    static double readFinite(DataInputStream in, String name) throws IOException {
        double value = in.readDouble();
        if (!Double.isFinite(value)) throw new ProtocolException(name + " must be finite");
        return value;
    }

    static double readPositiveFinite(DataInputStream in, String name) throws IOException {
        double value = readFinite(in, name);
        if (!(value > 0.0)) throw new ProtocolException(name + " must be positive");
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
        if (message == null || message.isBlank()) return "vector accelerator error";
        StringBuilder result = new StringBuilder(Math.min(message.length(), 512));
        for (int i = 0; i < message.length() && result.length() < 512; i++) {
            char c = message.charAt(i);
            if (c >= 0x20 && c != 0x7f) result.append(c);
        }
        return result.isEmpty() ? "vector accelerator error" : result.toString();
    }

    record RequestHeader(byte op, long requestId) {}
    record Hit(int index, double similarity) {}

    static final class ProtocolException extends IOException {
        ProtocolException(String message) {
            super(message);
        }
    }

    static List<Hit> topKForTest(
        double[] query,
        double queryNorm,
        List<double[]> vectors,
        double[] norms,
        int topK
    ) {
        if (query.length == 0) throw new IllegalArgumentException("empty query");
        if (vectors.size() != norms.length) throw new IllegalArgumentException("norm count");
        if (topK < 1 || topK > vectors.size()) throw new IllegalArgumentException("topK");

        var heap = new PriorityQueue<Hit>(
            topK,
            Comparator
                .comparingDouble(Hit::similarity)
                .thenComparing(Comparator.comparingInt(Hit::index).reversed())
        );

        for (int index = 0; index < vectors.size(); index++) {
            double[] vector = vectors.get(index);
            if (vector.length != query.length) throw new IllegalArgumentException("dimension mismatch");
            double dot = 0.0;
            for (int d = 0; d < query.length; d++) dot += query[d] * vector[d];
            var hit = new Hit(index, dot / (queryNorm * norms[index]));
            if (heap.size() < topK) heap.add(hit);
            else if (isBetter(hit, heap.peek())) {
                heap.poll();
                heap.add(hit);
            }
        }

        var ordered = new ArrayList<>(heap);
        ordered.sort(
            Comparator
                .comparingDouble(Hit::similarity)
                .reversed()
                .thenComparingInt(Hit::index)
        );
        return ordered;
    }

    static double norm(double[] vector) {
        double sum = 0.0;
        for (double value : vector) sum += value * value;
        return Math.sqrt(sum);
    }

    static void selfTest() {
        double[] query = {1.0, 0.0};
        var vectors = List.of(
            new double[] {1.0, 0.0},
            new double[] {0.0, 1.0},
            new double[] {-1.0, 0.0},
            new double[] {0.5, 0.5},
            new double[] {1.0, 0.0}
        );
        double[] norms = new double[vectors.size()];
        for (int i = 0; i < vectors.size(); i++) norms[i] = norm(vectors.get(i));

        var hits = topKForTest(query, norm(query), vectors, norms, 3);
        check(hits.size() == 3, "hit count");
        check(hits.get(0).index() == 0, "stable first tie");
        check(hits.get(1).index() == 4, "stable second tie");
        check(hits.get(2).index() == 3, "diagonal candidate");
        check(close(hits.get(0).similarity(), 1.0), "unit cosine");
        check(close(hits.get(2).similarity(), Math.sqrt(0.5)), "diagonal cosine");

        double[] flatQueries = {1.0, 0.0, -1.0, 0.0};
        double[] flatCandidates = new double[vectors.size() * 2];
        for (int i = 0; i < vectors.size(); i++) {
            flatCandidates[i * 2] = vectors.get(i)[0];
            flatCandidates[i * 2 + 1] = vectors.get(i)[1];
        }
        var positive = topKFlat(
            flatQueries, 0, 1.0, flatCandidates, norms, 2, vectors.size(), 2
        );
        var negative = topKFlat(
            flatQueries, 2, 1.0, flatCandidates, norms, 2, vectors.size(), 2
        );
        check(positive.get(0).index() == 0, "batch positive query");
        check(negative.get(0).index() == 2, "batch negative query");

        System.out.println("VectorSearchMain self-test: OK");
    }

    static boolean close(double a, double b) {
        return Math.abs(a - b) <= 1e-12 * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
    }

    static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError("self-test failed: " + name);
    }
}
