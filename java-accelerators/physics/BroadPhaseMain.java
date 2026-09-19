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
    static final byte OP_QUERY_AABBS = 4;
    static final byte OP_RAY_AABBS = 5;
    static final byte OP_SPHERE_CAST_AABBS = 6;

    static final byte STATUS_OK = 0;
    static final byte STATUS_BAD_REQUEST = 1;
    static final byte STATUS_INTERNAL = 2;

    static final int MAX_BODIES = 100_000;
    static final int MAX_PAIRS = 1_000_000;
    static final int MAX_QUERIES = 4096;
    static final int MAX_QUERY_HITS = 1_000_000;
    static final long MAX_SPATIAL_TESTS = 50_000_000L;
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
                    case OP_QUERY_AABBS -> handleQueryAabbs(in, out, header);
                    case OP_RAY_AABBS -> handleRayAabbs(in, out, header);
                    case OP_SPHERE_CAST_AABBS -> handleSphereCastAabbs(in, out, header);
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

    static void handleQueryAabbs(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int bodyCount = readBoundedInt(in, "body count", 0, MAX_BODIES);
        int queryCount = readBoundedInt(in, "query count", 1, MAX_QUERIES);
        int maxTotalHits = readBoundedInt(
            in,
            "max total hits",
            1,
            MAX_QUERY_HITS
        );

        var bodies = new Box[bodyCount];
        for (int i = 0; i < bodyCount; i++) {
            bodies[i] = readBounds(in, i);
        }
        var queries = new Box[queryCount];
        for (int i = 0; i < queryCount; i++) {
            queries[i] = readBounds(in, i);
        }

        QueryHits result = queryAabbs(bodies, queries, maxTotalHits);
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(result.counts().length);
        int offset = 0;
        for (int count : result.counts()) {
            out.writeInt(count);
            for (int index = 0; index < count; index++) {
                out.writeInt(result.indices()[offset++]);
            }
        }
    }

    static Box readBounds(DataInputStream in, int index) throws IOException {
        double minX = readFinite(in, "min x");
        double minY = readFinite(in, "min y");
        double minZ = readFinite(in, "min z");
        double maxX = readFinite(in, "max x");
        double maxY = readFinite(in, "max y");
        double maxZ = readFinite(in, "max z");
        Box box = new Box(
            index,
            false,
            minX,
            minY,
            minZ,
            maxX,
            maxY,
            maxZ
        );
        box.validate();
        return box;
    }

    static QueryHits queryAabbs(
        Box[] bodies,
        Box[] queries,
        int maxTotalHits
    ) {
        if (bodies.length > MAX_BODIES) {
            throw new IllegalArgumentException("body count");
        }
        if (queries.length < 1 || queries.length > MAX_QUERIES) {
            throw new IllegalArgumentException("query count");
        }
        if (maxTotalHits < 1 || maxTotalHits > MAX_QUERY_HITS) {
            throw new IllegalArgumentException("maxTotalHits");
        }
        if ((long) bodies.length * queries.length > MAX_SPATIAL_TESTS) {
            throw new IllegalArgumentException("spatial test bound exceeded");
        }
        for (Box body : bodies) {
            if (body == null) throw new IllegalArgumentException("null body box");
            body.validate();
        }
        for (Box query : queries) {
            if (query == null) throw new IllegalArgumentException("null query box");
            query.validate();
        }

        int[] counts = new int[queries.length];
        int[] indices = new int[maxTotalHits];
        int total = 0;
        for (int queryIndex = 0; queryIndex < queries.length; queryIndex++) {
            Box query = queries[queryIndex];
            int count = 0;
            for (int bodyIndex = 0; bodyIndex < bodies.length; bodyIndex++) {
                if (!query.overlaps(bodies[bodyIndex])) continue;
                if (total >= maxTotalHits) {
                    throw new QueryHitBoundException(
                        "AABB query total-hit bound exceeded"
                    );
                }
                indices[total++] = bodyIndex;
                count++;
            }
            counts[queryIndex] = count;
        }

        return new QueryHits(
            counts,
            java.util.Arrays.copyOf(indices, total)
        );
    }

    static void handleRayAabbs(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int bodyCount = readBoundedInt(in, "body count", 0, MAX_BODIES);
        int rayCount = readBoundedInt(in, "ray count", 1, MAX_QUERIES);
        int maxTotalHits = readBoundedInt(
            in,
            "max total candidates",
            1,
            MAX_QUERY_HITS
        );

        var bodies = new Box[bodyCount];
        for (int i = 0; i < bodyCount; i++) {
            bodies[i] = readBounds(in, i);
        }
        var rays = new RayQuery[rayCount];
        for (int i = 0; i < rayCount; i++) {
            rays[i] = readRay(in, i);
        }

        QueryHits result = rayAabbCandidates(
            bodies,
            rays,
            maxTotalHits
        );
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(result.counts().length);
        int offset = 0;
        for (int count : result.counts()) {
            out.writeInt(count);
            for (int index = 0; index < count; index++) {
                out.writeInt(result.indices()[offset++]);
            }
        }
    }

    static RayQuery readRay(
        DataInputStream in,
        int index
    ) throws IOException {
        RayQuery ray = new RayQuery(
            index,
            readFinite(in, "ray origin x"),
            readFinite(in, "ray origin y"),
            readFinite(in, "ray origin z"),
            readFinite(in, "ray direction x"),
            readFinite(in, "ray direction y"),
            readFinite(in, "ray direction z"),
            readFinite(in, "ray max distance")
        );
        ray.validate();
        return ray;
    }

    static QueryHits rayAabbCandidates(
        Box[] bodies,
        RayQuery[] rays,
        int maxTotalHits
    ) {
        if (bodies.length > MAX_BODIES) {
            throw new IllegalArgumentException("body count");
        }
        if (rays.length < 1 || rays.length > MAX_QUERIES) {
            throw new IllegalArgumentException("ray count");
        }
        if (maxTotalHits < 1 || maxTotalHits > MAX_QUERY_HITS) {
            throw new IllegalArgumentException("maxTotalHits");
        }
        if ((long) bodies.length * rays.length > MAX_SPATIAL_TESTS) {
            throw new IllegalArgumentException("spatial test bound exceeded");
        }
        for (Box body : bodies) {
            if (body == null) throw new IllegalArgumentException("null body box");
            body.validate();
        }
        for (RayQuery ray : rays) {
            if (ray == null) throw new IllegalArgumentException("null ray");
            ray.validate();
        }

        int[] counts = new int[rays.length];
        int[] indices = new int[maxTotalHits];
        int total = 0;
        for (int rayIndex = 0; rayIndex < rays.length; rayIndex++) {
            RayQuery ray = rays[rayIndex];
            int count = 0;
            for (int bodyIndex = 0; bodyIndex < bodies.length; bodyIndex++) {
                if (!ray.intersects(bodies[bodyIndex])) continue;
                if (total >= maxTotalHits) {
                    throw new QueryHitBoundException(
                        "ray candidate total-hit bound exceeded"
                    );
                }
                indices[total++] = bodyIndex;
                count++;
            }
            counts[rayIndex] = count;
        }
        return new QueryHits(
            counts,
            java.util.Arrays.copyOf(indices, total)
        );
    }

    static void handleSphereCastAabbs(
        DataInputStream in,
        DataOutputStream out,
        RequestHeader header
    ) throws IOException {
        int bodyCount = readBoundedInt(in, "body count", 0, MAX_BODIES);
        int rayCount = readBoundedInt(in, "sphere cast count", 1, MAX_QUERIES);
        int maxTotalHits = readBoundedInt(
            in,
            "max total candidates",
            1,
            MAX_QUERY_HITS
        );
        double radius = readFinite(in, "sphere cast radius");
        if (!(radius > 0.0)) {
            throw new ProtocolException("sphere cast radius must be positive");
        }

        var bodies = new Box[bodyCount];
        for (int i = 0; i < bodyCount; i++) {
            bodies[i] = readBounds(in, i);
        }
        var rays = new RayQuery[rayCount];
        for (int i = 0; i < rayCount; i++) {
            rays[i] = readRay(in, i);
        }

        QueryHits result = sphereCastAabbCandidates(
            bodies,
            rays,
            radius,
            maxTotalHits
        );
        writeHeader(out, header.op(), STATUS_OK, header.requestId());
        out.writeInt(result.counts().length);
        int offset = 0;
        for (int count : result.counts()) {
            out.writeInt(count);
            for (int index = 0; index < count; index++) {
                out.writeInt(result.indices()[offset++]);
            }
        }
    }

    static QueryHits sphereCastAabbCandidates(
        Box[] bodies,
        RayQuery[] rays,
        double radius,
        int maxTotalHits
    ) {
        if (bodies.length > MAX_BODIES) {
            throw new IllegalArgumentException("body count");
        }
        if (rays.length < 1 || rays.length > MAX_QUERIES) {
            throw new IllegalArgumentException("sphere cast count");
        }
        if (!Double.isFinite(radius) || !(radius > 0.0)) {
            throw new IllegalArgumentException("sphere cast radius");
        }
        if (maxTotalHits < 1 || maxTotalHits > MAX_QUERY_HITS) {
            throw new IllegalArgumentException("maxTotalHits");
        }
        if ((long) bodies.length * rays.length > MAX_SPATIAL_TESTS) {
            throw new IllegalArgumentException("spatial test bound exceeded");
        }
        for (Box body : bodies) {
            if (body == null) throw new IllegalArgumentException("null body box");
            body.validate();
        }
        for (RayQuery ray : rays) {
            if (ray == null) throw new IllegalArgumentException("null sphere cast");
            ray.validate();
        }

        int[] counts = new int[rays.length];
        int[] indices = new int[maxTotalHits];
        int total = 0;
        for (int rayIndex = 0; rayIndex < rays.length; rayIndex++) {
            RayQuery ray = rays[rayIndex];
            int count = 0;
            for (int bodyIndex = 0; bodyIndex < bodies.length; bodyIndex++) {
                if (!ray.intersects(bodies[bodyIndex], radius)) continue;
                if (total >= maxTotalHits) {
                    throw new QueryHitBoundException(
                        "sphere-cast candidate total-hit bound exceeded"
                    );
                }
                indices[total++] = bodyIndex;
                count++;
            }
            counts[rayIndex] = count;
        }
        return new QueryHits(
            counts,
            java.util.Arrays.copyOf(indices, total)
        );
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

    record QueryHits(int[] counts, int[] indices) {
        QueryHits {
            if (counts == null || indices == null) {
                throw new IllegalArgumentException("query hit arrays must not be null");
            }
        }
    }

    record RayQuery(
        int index,
        double originX,
        double originY,
        double originZ,
        double directionX,
        double directionY,
        double directionZ,
        double maxDistance
    ) {
        void validate() {
            if (index < 0) throw new IllegalArgumentException("negative ray index");
            if (
                !Double.isFinite(originX)
                || !Double.isFinite(originY)
                || !Double.isFinite(originZ)
                || !Double.isFinite(directionX)
                || !Double.isFinite(directionY)
                || !Double.isFinite(directionZ)
                || !Double.isFinite(maxDistance)
            ) {
                throw new IllegalArgumentException("non-finite ray component");
            }
            double normSq = (
                directionX * directionX
                + directionY * directionY
                + directionZ * directionZ
            );
            if (!(normSq > 0.0)) {
                throw new IllegalArgumentException("ray direction must be non-zero");
            }
            if (maxDistance < 0.0) {
                throw new IllegalArgumentException("ray max distance must be non-negative");
            }
        }

        boolean intersects(Box box) {
            return intersects(box, 0.0);
        }

        boolean intersects(Box box, double expansion) {
            if (!Double.isFinite(expansion) || expansion < 0.0) {
                throw new IllegalArgumentException("invalid AABB expansion");
            }
            double tMin = 0.0;
            double tMax = maxDistance;
            double[] origins = {originX, originY, originZ};
            double[] directions = {directionX, directionY, directionZ};
            double[] minimums = {
                box.minX() - expansion,
                box.minY() - expansion,
                box.minZ() - expansion,
            };
            double[] maximums = {
                box.maxX() + expansion,
                box.maxY() + expansion,
                box.maxZ() + expansion,
            };

            for (int axis = 0; axis < 3; axis++) {
                double origin = origins[axis];
                double direction = directions[axis];
                double minimum = minimums[axis];
                double maximum = maximums[axis];

                if (direction == 0.0) {
                    if (origin < minimum || origin > maximum) return false;
                    continue;
                }

                double inverse = 1.0 / direction;
                double near = (minimum - origin) * inverse;
                double far = (maximum - origin) * inverse;
                if (near > far) {
                    double swap = near;
                    near = far;
                    far = swap;
                }
                tMin = Math.max(tMin, near);
                tMax = Math.min(tMax, far);
                if (tMin > tMax + 1.0e-12) return false;
            }
            return tMax >= -1.0e-12 && tMin <= maxDistance + 1.0e-12;
        }
    }

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

    static final class QueryHitBoundException extends IllegalArgumentException {
        QueryHitBoundException(String message) { super(message); }
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

        QueryHits queryHits = queryAabbs(
            boxes,
            new Box[] {
                box(0, false, -0.5, -0.5, -0.5, 2.1, 2.1, 2.1),
                box(1, false, 9.5, 9.5, 9.5, 11.5, 11.5, 11.5),
            },
            100
        );
        check(
            java.util.Arrays.equals(queryHits.counts(), new int[] {4, 1}),
            "AABB query counts"
        );
        check(
            java.util.Arrays.equals(
                queryHits.indices(),
                new int[] {0, 1, 2, 4, 3}
            ),
            "AABB query stable body indices"
        );

        QueryHits rayHits = rayAabbCandidates(
            boxes,
            new RayQuery[] {
                new RayQuery(0, -1, 1, 1, 1, 0, 0, 20),
                new RayQuery(1, 9.5, 10.5, 10.5, 1, 0, 0, 5),
                new RayQuery(2, 0, 100, 0, 1, 0, 0, 5),
            },
            100
        );
        check(
            java.util.Arrays.equals(
                rayHits.counts(),
                new int[] {4, 1, 0}
            ),
            "ray AABB candidate counts"
        );
        check(
            java.util.Arrays.equals(
                rayHits.indices(),
                new int[] {0, 1, 2, 4, 3}
            ),
            "ray AABB candidate indices"
        );

        QueryHits sphereCastHits = sphereCastAabbCandidates(
            boxes,
            new RayQuery[] {
                new RayQuery(0, -1, 3.25, 1, 1, 0, 0, 20),
                new RayQuery(1, 8.5, 10.5, 10.5, 1, 0, 0, 5),
            },
            1.5,
            100
        );
        check(
            java.util.Arrays.equals(
                sphereCastHits.counts(),
                new int[] {4, 1}
            ),
            "sphere-cast AABB candidate counts"
        );
        check(
            java.util.Arrays.equals(
                sphereCastHits.indices(),
                new int[] {0, 1, 2, 4, 3}
            ),
            "sphere-cast AABB candidate indices"
        );

        boolean queryBoundRaised = false;
        try {
            queryAabbs(
                boxes,
                new Box[] {
                    box(0, false, -100, -100, -100, 100, 100, 100),
                },
                2
            );
        } catch (QueryHitBoundException expected) {
            queryBoundRaised = true;
        }
        check(queryBoundRaised, "AABB query hit bound");

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
