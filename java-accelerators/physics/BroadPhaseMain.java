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
import java.util.TreeSet;

/**
 * Optional finite-AABB broad-phase accelerator for Skeleton physics.
 *
 * <p>Python retains ownership of rigid bodies, shapes, infinite planes,
 * collision filtering, narrow phase, manifolds, caches, and the solver. This
 * helper receives only finite AABBs plus one "is dynamic" bit per body and
 * returns candidate index pairs. The protocol deliberately does not know body
 * IDs or shape types.</p>
 */
public final class BroadPhaseMain {
    static final int MAGIC = 0x534B4250; // SKBP
    static final short VERSION = 1;

    static final byte OP_PING = 1;
    static final byte OP_PAIRS = 2;
    static final byte OP_SHUTDOWN = 3;

    static final byte STATUS_OK = 0;
    static final byte STATUS_BAD_REQUEST = 1;
    static final byte STATUS_INTERNAL = 2;

    static final int MAX_BODIES = 100_000;
    static final int MAX_PAIRS = 1_000_000;
    static final int MAX_ERROR_BYTES = 8192;

    private BroadPhaseMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--stdio".equals(args[0])) {
            runService();
            return;
        }
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
            return;
        }
        System.err.println("usage: java BroadPhaseMain.java --stdio|--self-test");
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
                    case OP_PAIRS -> handlePairs(in, out, header);
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

    static void handlePairs(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int bodyCount = readBoundedInt(in, "body count", 0, MAX_BODIES);
        int maxPairs = readBoundedInt(in, "max pairs", 1, MAX_PAIRS);
        double epsilon = readFinite(in, "epsilon");
        if (epsilon < 0.0 || epsilon > 1.0) {
            throw new ProtocolException("epsilon outside [0, 1]");
        }

        var boxes = new Box[bodyCount];
        for (int i = 0; i < bodyCount; i++) {
            int dynamicFlag = in.readUnsignedByte();
            if (dynamicFlag > 1) {
                throw new ProtocolException("dynamic flag must be 0 or 1");
            }
            double minX = readFinite(in, "min x");
            double minY = readFinite(in, "min y");
            double minZ = readFinite(in, "min z");
            double maxX = readFinite(in, "max x");
            double maxY = readFinite(in, "max y");
            double maxZ = readFinite(in, "max z");
            boxes[i] = new Box(
                i,
                dynamicFlag == 1,
                minX,
                minY,
                minZ,
                maxX,
                maxY,
                maxZ
            );
        }

        List<Pair> pairs = computePairs(boxes, maxPairs, epsilon);
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(pairs.size());
        for (Pair pair : pairs) {
            out.writeInt(pair.left());
            out.writeInt(pair.right());
        }
    }

    static List<Pair> computePairs(Box[] boxes, int maxPairs, double epsilon) {
        if (boxes.length > MAX_BODIES) throw new IllegalArgumentException("body count");
        if (maxPairs < 1 || maxPairs > MAX_PAIRS) throw new IllegalArgumentException("maxPairs");
        if (!Double.isFinite(epsilon) || epsilon < 0.0) {
            throw new IllegalArgumentException("epsilon");
        }

        var ordered = new ArrayList<Box>(boxes.length);
        for (Box box : boxes) {
            if (box == null) throw new IllegalArgumentException("null box");
            box.validate();
            ordered.add(box);
        }
        ordered.sort(
            Comparator
                .comparingDouble(Box::minX)
                .thenComparingInt(Box::index)
        );

        var active = new TreeSet<Box>(
            Comparator
                .comparingDouble(Box::maxX)
                .thenComparingInt(Box::index)
        );
        var pairs = new ArrayList<Pair>();

        for (Box current : ordered) {
            while (!active.isEmpty()) {
                Box earliest = active.first();
                if (earliest.maxX() + epsilon >= current.minX()) break;
                active.pollFirst();
            }

            for (Box other : active) {
                if (!current.dynamic() && !other.dynamic()) continue;
                if (!current.overlaps(other)) continue;

                int left = Math.min(current.index(), other.index());
                int right = Math.max(current.index(), other.index());
                if (pairs.size() >= maxPairs) {
                    throw new PairBoundException("broad-phase pair bound exceeded");
                }
                pairs.add(new Pair(left, right));
            }
            active.add(current);
        }

        pairs.sort(
            Comparator
                .comparingInt(Pair::left)
                .thenComparingInt(Pair::right)
        );
        return pairs;
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
        if (message == null || message.isBlank()) return "broad-phase accelerator error";
        StringBuilder result = new StringBuilder(Math.min(message.length(), 512));
        for (int i = 0; i < message.length() && result.length() < 512; i++) {
            char c = message.charAt(i);
            if (c >= 0x20 && c != 0x7f) result.append(c);
        }
        return result.isEmpty() ? "broad-phase accelerator error" : result.toString();
    }

    record RequestHeader(byte op, long requestId) {}

    record Pair(int left, int right) {
        Pair {
            if (left < 0 || right <= left) {
                throw new IllegalArgumentException("pair indices must be strictly ordered");
            }
        }
    }

    record Box(
        int index,
        boolean dynamic,
        double minX,
        double minY,
        double minZ,
        double maxX,
        double maxY,
        double maxZ
    ) {
        void validate() {
            if (index < 0) throw new IllegalArgumentException("negative box index");
            if (
                !Double.isFinite(minX)
                || !Double.isFinite(minY)
                || !Double.isFinite(minZ)
                || !Double.isFinite(maxX)
                || !Double.isFinite(maxY)
                || !Double.isFinite(maxZ)
            ) {
                throw new IllegalArgumentException("non-finite AABB");
            }
            if (minX > maxX || minY > maxY || minZ > maxZ) {
                throw new IllegalArgumentException("AABB minimum exceeds maximum");
            }
        }

        boolean overlaps(Box other) {
            return !(
                maxX < other.minX
                || minX > other.maxX
                || maxY < other.minY
                || minY > other.maxY
                || maxZ < other.minZ
                || minZ > other.maxZ
            );
        }
    }

    static final class ProtocolException extends IOException {
        ProtocolException(String message) { super(message); }
    }

    static final class PairBoundException extends IllegalArgumentException {
        PairBoundException(String message) { super(message); }
    }

    static Box box(
        int index,
        boolean dynamic,
        double minX,
        double minY,
        double minZ,
        double maxX,
        double maxY,
        double maxZ
    ) {
        return new Box(index, dynamic, minX, minY, minZ, maxX, maxY, maxZ);
    }

    static void selfTest() {
        Box[] boxes = {
            box(0, true, 0, 0, 0, 2, 2, 2),
            box(1, false, 1, 1, 1, 3, 3, 3),
            box(2, false, 1.5, 1.5, 1.5, 4, 4, 4),
            box(3, true, 10, 10, 10, 11, 11, 11),
            box(4, true, 2, 2, 2, 2, 2, 2),
        };

        List<Pair> pairs = computePairs(boxes, 100, 1.0e-9);
        check(
            pairs.equals(List.of(
                new Pair(0, 1),
                new Pair(0, 2),
                new Pair(0, 4),
                new Pair(1, 4),
                new Pair(2, 4)
            )),
            "deterministic overlap pairs"
        );

        // Static-static AABBs overlap but do not form physical pairs.
        check(!pairs.contains(new Pair(1, 2)), "static-static filtered");

        // Touching bounds count as overlap, matching Python AABB.overlaps().
        Box[] touching = {
            box(0, true, 0, 0, 0, 1, 1, 1),
            box(1, false, 1, 0, 0, 2, 1, 1),
        };
        check(
            computePairs(touching, 10, 1.0e-9).equals(List.of(new Pair(0, 1))),
            "touching AABBs"
        );

        // X-axis epsilon only keeps near candidates active; full AABB rejection
        // still prevents a false pair when there is a real X gap.
        Box[] nearGap = {
            box(0, true, 0, 0, 0, 1, 1, 1),
            box(1, false, 1.0 + 5.0e-10, 0, 0, 2, 1, 1),
        };
        check(computePairs(nearGap, 10, 1.0e-9).isEmpty(), "full-AABB rejection");

        boolean boundRaised = false;
        try {
            computePairs(
                new Box[] {
                    box(0, true, 0, 0, 0, 2, 2, 2),
                    box(1, true, 0, 0, 0, 2, 2, 2),
                    box(2, true, 0, 0, 0, 2, 2, 2),
                },
                2,
                1.0e-9
            );
        } catch (PairBoundException expected) {
            boundRaised = true;
        }
        check(boundRaised, "pair bound");

        System.out.println("BroadPhaseMain self-test: OK");
    }

    static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError("self-test failed: " + name);
    }
}
