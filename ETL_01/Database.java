import java.sql.*;
import java.util.*;

/**
 * Thin JDBC wrapper around the SQLite analytics database.
 * Construct with a file path, call close() when done.
 */
public class Database {

    private final Connection conn;

    /**
     * Opens a connection to the SQLite file at {@code filePath}.
     * Throws SQLException (with a clear message) if the file can't be opened
     * or the required tables are missing.
     */
    public Database(String filePath) throws SQLException {
        // Explicitly load the driver — required when running from a plain
        // classpath (not a module path or fat JAR with service discovery).
        try {
            Class.forName("org.sqlite.JDBC");
        } catch (ClassNotFoundException e) {
            throw new SQLException(
                "SQLite JDBC driver not found. Make sure sqlite-jdbc.jar is on the classpath.", e);
        }

        String url = "jdbc:sqlite:" + filePath;
        conn = DriverManager.getConnection(url);

        // Validate that the expected tables exist before callers try to query them.
        validateTables();
    }

    // -----------------------------------------------------------------------
    // Validation
    // -----------------------------------------------------------------------

    /**
     * Returns a human-readable status string: table names found and row counts.
     * Throws SQLException if a required table is missing.
     */
    public String validateTables() throws SQLException {
        String[] required = {"teams", "players", "season_rosters"};
        StringBuilder sb = new StringBuilder();

        for (String table : required) {
            if (!tableExists(table)) {
                throw new SQLException("Required table not found: \"" + table + "\"");
            }
            int count = rowCount(table);
            sb.append(table).append(": ").append(count).append(" rows    ");
        }
        return sb.toString().trim();
    }

    private boolean tableExists(String name) throws SQLException {
        String sql = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, name);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() && rs.getInt(1) > 0;
            }
        }
    }

    private int rowCount(String table) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery("SELECT COUNT(*) FROM " + table)) {
            return rs.next() ? rs.getInt(1) : 0;
        }
    }

    // -----------------------------------------------------------------------
    // Teams
    // -----------------------------------------------------------------------

    /**
     * All teams ordered by name.
     * Display string: "Name (ABBR)" when abbreviation is present, else "Name".
     */
    public List<Team> getTeams() throws SQLException {
        List<Team> list = new ArrayList<>();
        String sql = "SELECT team_id, name, abbreviation FROM teams ORDER BY name";
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                int    id   = rs.getInt("team_id");
                String name = rs.getString("name");
                String abbr = rs.getString("abbreviation");
                String display = (abbr != null && !abbr.isBlank())
                    ? name + " (" + abbr + ")" : name;
                list.add(new Team(id, name, display));
            }
        }
        return list;
    }

    // -----------------------------------------------------------------------
    // Players
    // -----------------------------------------------------------------------

    /**
     * Players on the most recent season roster for {@code teamId},
     * ordered by name (stored as "Last, First").
     */
    public List<Player> getPlayersForTeam(int teamId) throws SQLException {
        List<Player> list = new ArrayList<>();
        String sql =
            "SELECT p.player_id, p.name, p.position, sr.jersey_number " +
            "FROM players p " +
            "JOIN season_rosters sr ON p.player_id = sr.player_id " +
            "WHERE sr.team_id = ? " +
            "  AND sr.season = (SELECT MAX(season) FROM season_rosters WHERE team_id = ?) " +
            "ORDER BY p.name";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, teamId);
            ps.setInt(2, teamId);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    list.add(new Player(
                        rs.getInt("player_id"),
                        rs.getString("name"),
                        rs.getString("position"),
                        rs.getInt("jersey_number")
                    ));
                }
            }
        }
        list.sort(Comparator.comparing(p -> {
            int sp = p.name == null ? -1 : p.name.lastIndexOf(' ');
            return sp >= 0 ? p.name.substring(sp + 1) : (p.name == null ? "" : p.name);
        }));
        return list;
    }

    // -----------------------------------------------------------------------
    // Lifecycle
    // -----------------------------------------------------------------------

    public void close() {
        try { if (conn != null && !conn.isClosed()) conn.close(); }
        catch (SQLException ignored) {}
    }

    // -----------------------------------------------------------------------
    // Value objects
    // -----------------------------------------------------------------------

    public static class Team {
        public final int    id;
        public final String name;
        public final String display;

        Team(int id, String name, String display) {
            this.id = id; this.name = name; this.display = display;
        }

        @Override public String toString() { return display; }
    }

    public static class Player {
        public final int    id;
        public final String name;
        public final String position;
        public final int    jerseyNumber;

        Player(int id, String name, String position, int jerseyNumber) {
            this.id = id; this.name = name;
            this.position = position; this.jerseyNumber = jerseyNumber;
        }

        @Override public String toString() {
            String pos = (position != null && !position.isBlank()) ? "  (" + position + ")" : "";
            return "#" + jerseyNumber + "  " + name + pos;
        }
    }
}
