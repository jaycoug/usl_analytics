import javax.swing.*;
import javax.swing.border.*;
import java.awt.*;
import java.awt.event.*;
import java.sql.SQLException;
import java.util.*;
import java.util.List;

public class USLExtractorGUI extends JFrame {

    // -----------------------------------------------------------------------
    // Database
    // -----------------------------------------------------------------------

    private Database db;
    private List<Database.Team> allTeams = new ArrayList<>();

    // -----------------------------------------------------------------------
    // Position data
    // -----------------------------------------------------------------------

    private Point teamSelectPos;
    private Point playerSelectPos;
    private Point spreadsheetTargetPos;
    private Point spreadsheetWindowPos;
    private Point tableSelectStart, tableSelectEnd;
    private Point[] statCategoryPos  = new Point[5];
    private Point[] removePlayersPos = new Point[2]; // [0]=first player, [1]=remaining four

    // Down-arrow counts per stat tab iteration (tabs 1–5)
    private static final int[] STAT_DOWN_ARROWS = {6, 5, 12, 6, 5};

    // -----------------------------------------------------------------------
    // UI labels (positions)
    // -----------------------------------------------------------------------

    private JLabel teamSelectLabel, playerSelectLabel;
    private JLabel spreadsheetTargetLabel, spreadsheetWindowLabel;
    private JLabel tableStartLabel, tableEndLabel;
    private JLabel[] statCategoryLabels  = new JLabel[5];
    private JLabel   removePlayers1Label, removePlayers2Label;

    // -----------------------------------------------------------------------
    // Other UI
    // -----------------------------------------------------------------------

    private JLabel                    statusLabel;
    private JButton                   extractCurrentButton;
    private JButton                   extractTeamBtn;
    private JSpinner                  mouseStepDelaySpinner, actionIntervalSpinner;
    private JComboBox<Database.Team>  teamComboBox;
    private DefaultListModel<Database.Player> playerListModel = new DefaultListModel<>();
    private JList<Database.Player>    playerJList;

    private Database.Player pivotGK  = null;
    private JLabel          pivotGKLabel;

    private static final Dimension TUNE_BTN_SIZE = new Dimension(70, 26);

    // -----------------------------------------------------------------------
    // Category enum
    // -----------------------------------------------------------------------

    enum Category {
        TEAM_SELECT, PLAYER_SELECT, STAT_CATEGORY, REMOVE_PLAYERS,
        TABLE_SELECT, SPREADSHEET_TARGET, SPREADSHEET_WINDOW
    }

    private static final Category[] TUNE_ALL_SEQUENCE = {
        Category.TEAM_SELECT,
        Category.PLAYER_SELECT,
        Category.STAT_CATEGORY,
        Category.REMOVE_PLAYERS,
        Category.TABLE_SELECT,
        Category.SPREADSHEET_TARGET,
        Category.SPREADSHEET_WINDOW
    };

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    public USLExtractorGUI() {
        // DB is not opened here — the user connects explicitly via the Set Team tab.

        setTitle("USL Extractor");
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setAlwaysOnTop(true);
        setLayout(new BorderLayout(10, 10));
        ((JPanel) getContentPane()).setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));

        statusLabel = new JLabel("Click 'Tune All' or tune individual positions.", SwingConstants.CENTER);
        add(statusLabel, BorderLayout.NORTH);

        JTabbedPane tabs = new JTabbedPane();
        tabs.addTab("Position", buildPositionTab());
        tabs.addTab("Set Team", buildSetTeamTab());
        add(tabs, BorderLayout.CENTER);

        add(buildBottomPanel(), BorderLayout.SOUTH);

        pack();
        setMinimumSize(new Dimension(540, 480));
        setPreferredSize(new Dimension(580, 620));
        pack();
        setLocationRelativeTo(null);
    }

    // -----------------------------------------------------------------------
    // Tab: Position
    // -----------------------------------------------------------------------

    private JPanel buildPositionTab() {
        JPanel tab = new JPanel(new BorderLayout(0, 8));
        tab.setBorder(BorderFactory.createEmptyBorder(8, 4, 8, 4));

        // Tune All at top
        JPanel tuneAllBar = new JPanel(new FlowLayout(FlowLayout.LEFT, 0, 0));
        JButton tuneAllBtn = new JButton("Tune All");
        tuneAllBtn.addActionListener(e -> startTuneAll());
        tuneAllBar.add(tuneAllBtn);
        tab.add(tuneAllBar, BorderLayout.NORTH);

        // Scrollable position rows
        JScrollPane scroll = new JScrollPane(buildPositionsPanel());
        scroll.setBorder(null);
        scroll.getVerticalScrollBar().setUnitIncrement(12);
        tab.add(scroll, BorderLayout.CENTER);

        // Timing settings at bottom of tab
        tab.add(buildTimingPanel(), BorderLayout.SOUTH);

        return tab;
    }

    private JPanel buildTimingPanel() {
        JPanel p = new JPanel(new GridLayout(2, 2, 5, 5));
        p.setBorder(BorderFactory.createTitledBorder("Timing Settings"));
        mouseStepDelaySpinner = new JSpinner(new SpinnerNumberModel(15,   1, 5000, 1));
        actionIntervalSpinner = new JSpinner(new SpinnerNumberModel(700, 10, 5000, 10));
        p.add(new JLabel("Mouse step delay (ms/step):"));
        p.add(mouseStepDelaySpinner);
        p.add(new JLabel("Action interval (ms):"));
        p.add(actionIntervalSpinner);
        return p;
    }

    private JPanel buildPositionsPanel() {
        teamSelectLabel        = new JLabel("Not set");
        playerSelectLabel      = new JLabel("Not set");
        tableStartLabel        = new JLabel("Not set");
        tableEndLabel          = new JLabel("Not set");
        spreadsheetTargetLabel = new JLabel("Not set");
        spreadsheetWindowLabel = new JLabel("Not set");
        removePlayers1Label    = new JLabel("Not set");
        removePlayers2Label    = new JLabel("Not set");
        for (int i = 0; i < 5; i++) statCategoryLabels[i] = new JLabel("Not set");

        JPanel p = new JPanel();
        p.setLayout(new BoxLayout(p, BoxLayout.Y_AXIS));
        p.setBorder(BorderFactory.createTitledBorder("Positions"));

        p.add(singleRow("Team Select",        teamSelectLabel,        Category.TEAM_SELECT));
        p.add(vgap());
        p.add(singleRow("Player Select",      playerSelectLabel,      Category.PLAYER_SELECT));
        p.add(vgap());
        p.add(multiRow("Stat Category",       statCategoryLabels,     Category.STAT_CATEGORY,
                       "Set first 2 — remaining 3 extrapolated rightward"));
        p.add(vgap());
        p.add(removePlayersRow());
        p.add(vgap());
        p.add(dragRow());
        p.add(vgap());
        p.add(singleRow("Spreadsheet Target", spreadsheetTargetLabel, Category.SPREADSHEET_TARGET));
        p.add(vgap());
        p.add(singleRow("Spreadsheet Window", spreadsheetWindowLabel, Category.SPREADSHEET_WINDOW));

        return p;
    }

    // -----------------------------------------------------------------------
    // Tab: Set Team
    // -----------------------------------------------------------------------

    // Set Team tab sub-components that need to be accessed across methods
    private JTextField        dbPathField;
    private JLabel            dbStatusLabel;
    private JButton           connectButton;

    private JPanel buildSetTeamTab() {
        JPanel tab = new JPanel(new BorderLayout(10, 10));
        tab.setBorder(BorderFactory.createEmptyBorder(12, 10, 12, 10));

        // ── Database connection panel ─────────────────────────────────────────
        JPanel dbPanel = new JPanel(new BorderLayout(6, 4));
        dbPanel.setBorder(BorderFactory.createTitledBorder("Database"));

        // File path row
        JPanel pathRow = new JPanel(new BorderLayout(6, 0));
        dbPathField = new JTextField(System.getProperty("user.dir") + "/usl_championship.db");
        JButton browseBtn = new JButton("Browse…");
        browseBtn.addActionListener(e -> {
            JFileChooser fc = new JFileChooser(System.getProperty("user.dir"));
            fc.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(
                "SQLite databases (*.db)", "db"));
            if (fc.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
                dbPathField.setText(fc.getSelectedFile().getAbsolutePath());
            }
        });
        pathRow.add(new JLabel("File:"), BorderLayout.WEST);
        pathRow.add(dbPathField,         BorderLayout.CENTER);
        pathRow.add(browseBtn,           BorderLayout.EAST);

        // Connect button + status row
        JPanel connectRow = new JPanel(new BorderLayout(6, 0));
        connectButton  = new JButton("Connect");
        dbStatusLabel  = new JLabel("Not connected.", SwingConstants.LEFT);
        dbStatusLabel.setForeground(Color.GRAY);
        connectButton.addActionListener(e -> connectToDatabase());
        connectRow.add(connectButton,  BorderLayout.WEST);
        connectRow.add(dbStatusLabel,  BorderLayout.CENTER);

        dbPanel.add(pathRow,    BorderLayout.NORTH);
        dbPanel.add(connectRow, BorderLayout.SOUTH);

        // ── Team selector ─────────────────────────────────────────────────────
        JPanel teamRow = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
        teamRow.setBorder(BorderFactory.createTitledBorder("Session Team"));
        teamRow.add(new JLabel("Team:"));
        teamComboBox = new JComboBox<>();
        teamComboBox.setPreferredSize(new Dimension(280, 26));
        teamComboBox.setEnabled(false);
        teamComboBox.addActionListener(e -> refreshPlayerList());
        teamRow.add(teamComboBox);

        // ── Player roster list ────────────────────────────────────────────────
        playerJList = new JList<>(playerListModel);
        playerJList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        JScrollPane playerScroll = new JScrollPane(playerJList);

        JButton moveUpBtn   = new JButton("▲");
        JButton moveDownBtn = new JButton("▼");
        moveUpBtn.addActionListener(e -> movePlayer(-1));
        moveDownBtn.addActionListener(e -> movePlayer(1));
        JPanel orderButtons = new JPanel(new GridLayout(2, 1, 0, 4));
        orderButtons.add(moveUpBtn);
        orderButtons.add(moveDownBtn);

        JPanel rosterPanel = new JPanel(new BorderLayout(4, 0));
        rosterPanel.setBorder(BorderFactory.createTitledBorder("Roster (drag ▲/▼ to reorder for Extract Team)"));
        rosterPanel.add(playerScroll,  BorderLayout.CENTER);
        rosterPanel.add(orderButtons,  BorderLayout.EAST);

        // Stack the top controls
        JPanel topStack = new JPanel();
        topStack.setLayout(new BoxLayout(topStack, BoxLayout.Y_AXIS));
        topStack.add(dbPanel);
        topStack.add(Box.createVerticalStrut(6));
        topStack.add(teamRow);

        // ── Pivot GK selector ─────────────────────────────────────────────────
        pivotGKLabel = new JLabel("None selected", SwingConstants.LEFT);
        pivotGKLabel.setForeground(Color.GRAY);
        JButton setPivotBtn = new JButton("Set from Selection");
        setPivotBtn.addActionListener(e -> setPivotGK());
        JPanel pivotGKPanel = new JPanel(new BorderLayout(6, 0));
        pivotGKPanel.setBorder(BorderFactory.createTitledBorder("Pivot GK (always in stats table)"));
        pivotGKPanel.add(pivotGKLabel, BorderLayout.CENTER);
        pivotGKPanel.add(setPivotBtn,  BorderLayout.EAST);

        tab.add(topStack,     BorderLayout.NORTH);
        tab.add(rosterPanel,  BorderLayout.CENTER);
        tab.add(pivotGKPanel, BorderLayout.SOUTH);

        return tab;
    }

    /** Called when the user clicks Connect. */
    private void connectToDatabase() {
        String path = dbPathField.getText().trim();
        if (path.isEmpty()) {
            dbStatusLabel.setForeground(Color.RED);
            dbStatusLabel.setText("Please enter a database file path.");
            return;
        }

        connectButton.setEnabled(false);
        dbStatusLabel.setForeground(Color.GRAY);
        dbStatusLabel.setText("Connecting…");

        // Run on background thread so the EDT stays responsive
        new Thread(() -> {
            String statusText;
            Color  statusColor;
            List<Database.Team> teams = new ArrayList<>();

            try {
                if (db != null) db.close();
                db = new Database(path);
                String tableInfo = db.validateTables();
                teams      = db.getTeams();
                statusText  = "Connected — " + tableInfo;
                statusColor = new Color(0, 140, 0);
            } catch (SQLException ex) {
                statusText  = "Error: " + ex.getMessage();
                statusColor = Color.RED;
                db = null;
            }

            final List<Database.Team> finalTeams = teams;
            final String finalStatus = statusText;
            final Color  finalColor  = statusColor;

            SwingUtilities.invokeLater(() -> {
                dbStatusLabel.setText(finalStatus);
                dbStatusLabel.setForeground(finalColor);
                connectButton.setEnabled(true);

                teamComboBox.setModel(
                    new DefaultComboBoxModel<>(finalTeams.toArray(new Database.Team[0])));
                teamComboBox.setEnabled(!finalTeams.isEmpty());
                refreshPlayerList();
            });
        }).start();
    }

    /** Reload players for the currently selected team. */
    private void refreshPlayerList() {
        playerListModel.clear();
        pivotGK = null;
        if (pivotGKLabel != null) {
            pivotGKLabel.setText("None selected");
            pivotGKLabel.setForeground(Color.GRAY);
        }
        Database.Team selected = (Database.Team) teamComboBox.getSelectedItem();
        if (selected == null || db == null) return;
        try {
            for (Database.Player p : db.getPlayersForTeam(selected.id))
                playerListModel.addElement(p);
        } catch (SQLException ignored) {}
        refreshExtractButton();
    }

    /** Move the selected roster player up (-1) or down (+1). */
    private void movePlayer(int direction) {
        int idx    = playerJList.getSelectedIndex();
        int newIdx = idx + direction;
        if (idx < 0 || newIdx < 0 || newIdx >= playerListModel.size()) return;
        Database.Player p = playerListModel.remove(idx);
        playerListModel.add(newIdx, p);
        playerJList.setSelectedIndex(newIdx);
    }

    /**
     * Returns the current roster order as an ordered list.
     * Used by Extract Team sequence to determine player processing order.
     */
    private List<Database.Player> getRosterOrder() {
        List<Database.Player> ordered = new ArrayList<>();
        for (int i = 0; i < playerListModel.size(); i++)
            ordered.add(playerListModel.getElementAt(i));
        return ordered;
    }

    /** Mark the currently selected roster player as the Pivot GK. */
    private void setPivotGK() {
        Database.Player selected = playerJList.getSelectedValue();
        if (selected == null) {
            JOptionPane.showMessageDialog(this, "Select a player in the roster first.");
            return;
        }
        pivotGK = selected;
        pivotGKLabel.setText(pivotGK.toString());
        pivotGKLabel.setForeground(new Color(0, 120, 0));
        refreshExtractButton();
    }

    // -----------------------------------------------------------------------
    // Bottom panel — always visible across all tabs
    // -----------------------------------------------------------------------

    private JPanel buildBottomPanel() {
        JPanel p = new JPanel(new FlowLayout(FlowLayout.CENTER, 10, 6));
        p.setBorder(BorderFactory.createMatteBorder(1, 0, 0, 0, Color.LIGHT_GRAY));

        extractCurrentButton = new JButton("Extract Current");
        extractTeamBtn       = new JButton("Extract Team");
        JButton extractLeagueBtn = new JButton("Extract League");

        extractCurrentButton.setEnabled(false);
        extractTeamBtn.setEnabled(false);
        extractLeagueBtn.setEnabled(false);  // defined later

        extractCurrentButton.addActionListener(e -> runExtract());
        extractTeamBtn.addActionListener(e -> runExtractTeam());

        p.add(extractCurrentButton);
        p.add(extractTeamBtn);
        p.add(extractLeagueBtn);
        return p;
    }

    // -----------------------------------------------------------------------
    // Row builders
    // -----------------------------------------------------------------------

    private JPanel singleRow(String title, JLabel valueLabel, Category cat) {
        JPanel row = new JPanel(new BorderLayout(8, 0));
        row.setBorder(categoryBorder(title));
        row.add(valueLabel, BorderLayout.CENTER);
        row.add(tuneButton(cat), BorderLayout.EAST);
        return row;
    }

    private JPanel multiRow(String title, JLabel[] labels, Category cat, String hint) {
        JPanel row = new JPanel(new BorderLayout(8, 0));
        row.setBorder(categoryBorder(title));

        JPanel grid = new JPanel(new GridLayout(5, 2, 4, 2));
        for (int i = 0; i < 5; i++) {
            JLabel idx = new JLabel("#" + (i + 1) + ":");
            idx.setForeground(Color.GRAY);
            grid.add(idx);
            grid.add(labels[i]);
        }

        JPanel center = new JPanel(new BorderLayout(0, 2));
        JLabel hintLabel = new JLabel(hint);
        hintLabel.setFont(hintLabel.getFont().deriveFont(Font.ITALIC, 10f));
        hintLabel.setForeground(Color.GRAY);
        center.add(hintLabel, BorderLayout.NORTH);
        center.add(grid,      BorderLayout.CENTER);
        row.add(center, BorderLayout.CENTER);
        row.add(tuneButton(cat), BorderLayout.EAST);
        return row;
    }

    private JPanel dragRow() {
        JPanel row = new JPanel(new BorderLayout(8, 0));
        row.setBorder(categoryBorder("Table Select"));

        JPanel grid = new JPanel(new GridLayout(2, 2, 4, 2));
        JLabel sl = new JLabel("Start:"); sl.setForeground(Color.GRAY);
        JLabel el = new JLabel("End:");   el.setForeground(Color.GRAY);
        grid.add(sl); grid.add(tableStartLabel);
        grid.add(el); grid.add(tableEndLabel);
        row.add(grid, BorderLayout.CENTER);
        row.add(tuneButton(Category.TABLE_SELECT), BorderLayout.EAST);
        return row;
    }

    private JPanel removePlayersRow() {
        JPanel row = new JPanel(new BorderLayout(8, 0));
        row.setBorder(categoryBorder("Remove Players"));

        JPanel grid = new JPanel(new GridLayout(2, 2, 4, 2));
        JLabel fl = new JLabel("First:");     fl.setForeground(Color.GRAY);
        JLabel rl = new JLabel("Remaining:"); rl.setForeground(Color.GRAY);
        grid.add(fl); grid.add(removePlayers1Label);
        grid.add(rl); grid.add(removePlayers2Label);

        JPanel center = new JPanel(new BorderLayout(0, 2));
        JLabel hint = new JLabel("Click 1× at First, then 4× at Remaining (≥700 ms between each)");
        hint.setFont(hint.getFont().deriveFont(Font.ITALIC, 10f));
        hint.setForeground(Color.GRAY);
        center.add(hint, BorderLayout.NORTH);
        center.add(grid, BorderLayout.CENTER);
        row.add(center, BorderLayout.CENTER);
        row.add(tuneButton(Category.REMOVE_PLAYERS), BorderLayout.EAST);
        return row;
    }

    private TitledBorder categoryBorder(String title) {
        TitledBorder b = BorderFactory.createTitledBorder(
                BorderFactory.createEtchedBorder(), title);
        b.setTitleFont(b.getTitleFont().deriveFont(Font.BOLD, 11f));
        return b;
    }

    private JButton tuneButton(Category cat) {
        JButton btn = new JButton("Tune");
        btn.setPreferredSize(TUNE_BTN_SIZE);
        btn.setMinimumSize(TUNE_BTN_SIZE);
        btn.setMaximumSize(TUNE_BTN_SIZE);
        btn.addActionListener(e -> startCapture(cat, null));
        return btn;
    }

    private Component vgap() { return Box.createVerticalStrut(6); }

    // -----------------------------------------------------------------------
    // Tune All
    // -----------------------------------------------------------------------

    private void startTuneAll() { runTuneSequence(0); }

    private void runTuneSequence(int index) {
        if (index >= TUNE_ALL_SEQUENCE.length) {
            statusLabel.setText("All positions set. Click 'Extract Current' to run.");
            refreshExtractButton();
            return;
        }
        startCapture(TUNE_ALL_SEQUENCE[index], () -> runTuneSequence(index + 1));
    }

    // -----------------------------------------------------------------------
    // Generic position capture
    // -----------------------------------------------------------------------

    private void startCapture(Category cat, Runnable onComplete) {
        statusLabel.setText("Setting: " + categoryName(cat));
        Dimension screen = Toolkit.getDefaultToolkit().getScreenSize();

        JWindow instrWin = new JWindow();
        instrWin.setAlwaysOnTop(true);

        JLabel instrLabel = new JLabel(firstInstruction(cat), SwingConstants.CENTER);
        instrLabel.setFont(new Font("SansSerif", Font.BOLD, 15));
        instrLabel.setForeground(Color.WHITE);
        instrLabel.setBackground(new Color(30, 60, 150));
        instrLabel.setOpaque(true);
        instrLabel.setBorder(BorderFactory.createEmptyBorder(8, 20, 8, 20));

        JButton cancelBtn = new JButton("Cancel");
        cancelBtn.setFocusable(false);

        JPanel instrPanel = new JPanel(new BorderLayout(5, 0));
        instrPanel.setBackground(new Color(30, 60, 150));
        instrPanel.add(instrLabel, BorderLayout.CENTER);
        instrPanel.add(cancelBtn,  BorderLayout.EAST);
        instrWin.setContentPane(instrPanel);
        instrWin.pack();
        instrWin.setLocation((screen.width - instrWin.getWidth()) / 2, 5);

        JWindow overlay = new JWindow();
        overlay.setBounds(0, 0, screen.width, screen.height);

        GraphicsDevice gd = GraphicsEnvironment.getLocalGraphicsEnvironment().getDefaultScreenDevice();
        if (gd.isWindowTranslucencySupported(GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSLUCENT)) {
            overlay.setBackground(new Color(0, 0, 0, 0));
            JPanel glass = new JPanel() {
                @Override protected void paintComponent(Graphics g) {
                    g.setColor(new Color(0, 0, 0, 20));
                    g.fillRect(0, 0, getWidth(), getHeight());
                }
            };
            glass.setOpaque(false);
            overlay.setContentPane(glass);
        } else {
            try { overlay.setOpacity(0.10f); } catch (UnsupportedOperationException ignored) {}
        }

        int[]   clickCount = {0};
        Point[] temp       = new Point[2];

        Runnable finish = () -> {
            overlay.dispose();
            instrWin.dispose();
            setVisible(true);
            refreshExtractButton();
            if (onComplete != null) SwingUtilities.invokeLater(onComplete);
        };

        cancelBtn.addActionListener(e -> {
            overlay.dispose();
            instrWin.dispose();
            statusLabel.setText("Capture cancelled.");
            setVisible(true);
        });

        overlay.addMouseListener(new MouseAdapter() {
            @Override
            public void mousePressed(MouseEvent e) {
                int sx = e.getXOnScreen();
                int sy = e.getYOnScreen();
                clickCount[0]++;

                switch (cat) {

                    case TEAM_SELECT:
                    case PLAYER_SELECT:
                    case SPREADSHEET_TARGET:
                    case SPREADSHEET_WINDOW:
                        applyPoint(cat, 0, new Point(sx, sy));
                        finish.run();
                        break;

                    case REMOVE_PLAYERS:
                    case TABLE_SELECT:
                        if (clickCount[0] == 1) {
                            temp[0] = new Point(sx, sy);
                            instrLabel.setText(secondInstruction(cat));
                            repack(instrWin, screen);
                        } else {
                            applyPoint(cat, 0, temp[0]);
                            applyPoint(cat, 1, new Point(sx, sy));
                            finish.run();
                        }
                        break;

                    case STAT_CATEGORY:
                        if (clickCount[0] == 1) {
                            temp[0] = new Point(sx, sy);
                            instrLabel.setText("Click target 2 of 2 (3–5 will be extrapolated)");
                            repack(instrWin, screen);
                        } else {
                            temp[1] = new Point(sx, sy);
                            int dx = temp[1].x - temp[0].x;
                            int dy = temp[1].y - temp[0].y;
                            for (int i = 0; i < 5; i++) {
                                applyPoint(cat, i, new Point(temp[0].x + dx * i, temp[0].y + dy * i));
                            }
                            finish.run();
                        }
                        break;
                }
            }
        });

        setVisible(false);
        overlay.setVisible(true);
        instrWin.setVisible(true);
        overlay.toFront();
    }

    private void repack(JWindow win, Dimension screen) {
        win.pack();
        win.setLocation((screen.width - win.getWidth()) / 2, 5);
    }

    // -----------------------------------------------------------------------
    // Apply point to model + label
    // -----------------------------------------------------------------------

    private void applyPoint(Category cat, int index, Point p) {
        String coord = p.x + ", " + p.y;
        switch (cat) {
            case TEAM_SELECT:
                teamSelectPos = p;
                teamSelectLabel.setText(coord);
                break;
            case PLAYER_SELECT:
                playerSelectPos = p;
                playerSelectLabel.setText(coord);
                break;
            case TABLE_SELECT:
                if (index == 0) { tableSelectStart = p; tableStartLabel.setText(coord); }
                else            { tableSelectEnd   = p; tableEndLabel.setText(coord);   }
                break;
            case SPREADSHEET_TARGET:
                spreadsheetTargetPos = p;
                spreadsheetTargetLabel.setText(coord);
                break;
            case SPREADSHEET_WINDOW:
                spreadsheetWindowPos = p;
                spreadsheetWindowLabel.setText(coord);
                break;
            case STAT_CATEGORY:
                statCategoryPos[index] = p;
                statCategoryLabels[index].setText(coord);
                break;
            case REMOVE_PLAYERS:
                removePlayersPos[index] = p;
                if (index == 0) removePlayers1Label.setText(coord);
                else            removePlayers2Label.setText(coord);
                break;
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    private String categoryName(Category cat) {
        switch (cat) {
            case TEAM_SELECT:        return "Team Select";
            case PLAYER_SELECT:      return "Player Select";
            case STAT_CATEGORY:      return "Stat Category";
            case REMOVE_PLAYERS:     return "Remove Players";
            case TABLE_SELECT:       return "Table Select";
            case SPREADSHEET_TARGET: return "Spreadsheet Target";
            case SPREADSHEET_WINDOW: return "Spreadsheet Window";
            default:                 return cat.name();
        }
    }

    private String firstInstruction(Category cat) {
        switch (cat) {
            case TEAM_SELECT:        return "Click: Team Select dropdown";
            case PLAYER_SELECT:      return "Click: Player Select dropdown";
            case STAT_CATEGORY:      return "Click target 1 of 2: first Stat Category tab";
            case REMOVE_PLAYERS:     return "Click: Remove Players position for first player";
            case TABLE_SELECT:       return "Click Position 1: start of drag selection";
            case SPREADSHEET_TARGET: return "Click: Spreadsheet target cell";
            case SPREADSHEET_WINDOW: return "Click: Spreadsheet window (paste anchor)";
            default:                 return "Click to set position";
        }
    }

    private String secondInstruction(Category cat) {
        switch (cat) {
            case REMOVE_PLAYERS: return "Click: Remove Players position for remaining players";
            case TABLE_SELECT:   return "Click Position 2: end of drag selection";
            default:             return "Click to set second position";
        }
    }

    private boolean allPositionsSet() {
        if (teamSelectPos == null || playerSelectPos == null)             return false;
        if (tableSelectStart == null || tableSelectEnd == null)           return false;
        if (spreadsheetTargetPos == null || spreadsheetWindowPos == null) return false;
        if (removePlayersPos[0] == null || removePlayersPos[1] == null)   return false;
        for (Point p : statCategoryPos) if (p == null) return false;
        return true;
    }

    private void refreshExtractButton() {
        boolean pos = allPositionsSet();
        extractCurrentButton.setEnabled(pos);
        extractTeamBtn.setEnabled(pos && pivotGK != null);
        if (pos)
            statusLabel.setText("All positions set. Click 'Extract Current' to run.");
    }

    // -----------------------------------------------------------------------
    // Robot helpers
    // -----------------------------------------------------------------------

    private void smoothMouseMove(Robot r, int x0, int y0, int x1, int y1, int steps, int stepDelayMs) {
        double dx = (x1 - x0) / (double) steps;
        double dy = (y1 - y0) / (double) steps;
        for (int i = 0; i <= steps; i++) {
            r.mouseMove((int) (x0 + dx * i), (int) (y0 + dy * i));
            r.delay(stepDelayMs);
        }
    }

    private int[] moveTo(Robot r, int fx, int fy, int tx, int ty, int stepDelay, int interval) {
        smoothMouseMove(r, fx, fy, tx, ty, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        return new int[]{tx, ty};
    }

    private int[] dragCopyTable(Robot r, int fx, int fy, int stepDelay, int interval) {
        smoothMouseMove(r, fx, fy, tableSelectStart.x, tableSelectStart.y, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        smoothMouseMove(r, tableSelectStart.x, tableSelectStart.y,
                           tableSelectEnd.x,   tableSelectEnd.y, 30, stepDelay);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_C);
        r.delay(interval);
        r.keyRelease(KeyEvent.VK_C);
        r.keyRelease(KeyEvent.VK_CONTROL);
        r.delay(interval);
        return new int[]{tableSelectEnd.x, tableSelectEnd.y};
    }

    private void copySelection(Robot r, int interval) {
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_C);
        r.delay(interval);
        r.keyRelease(KeyEvent.VK_C);
        r.keyRelease(KeyEvent.VK_CONTROL);
        r.delay(interval);
    }

    private int[] clickDownArrowsPaste(Robot r, int fx, int fy, Point target,
                                       int downCount, int stepDelay, int interval) {
        smoothMouseMove(r, fx, fy, target.x, target.y, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        for (int i = 0; i < downCount; i++) {
            r.keyPress(KeyEvent.VK_DOWN);
            r.keyRelease(KeyEvent.VK_DOWN);
            r.delay(50);
        }
        r.delay(interval);
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_V);
        r.delay(interval);
        r.keyRelease(KeyEvent.VK_V);
        r.keyRelease(KeyEvent.VK_CONTROL);
        r.delay(interval);
        return new int[]{target.x, target.y};
    }

    // -----------------------------------------------------------------------
    // Pause dialog — shown after the first paste
    // -----------------------------------------------------------------------

    /**
     * Blocks the calling (non-EDT) thread with a modal dialog.
     * Returns true if the user clicks Continue / presses Enter.
     * Returns false if the user clicks Cancel / presses Escape → caller ends the extraction sequence only.
     */
    private boolean waitForUserContinue() {
        final boolean[] proceed = {false};
        try {
            SwingUtilities.invokeAndWait(() -> {
                JDialog dialog = new JDialog((Frame) null, "Continue?", true);
                dialog.setAlwaysOnTop(true);
                dialog.setLayout(new BorderLayout(10, 10));
                ((JPanel) dialog.getContentPane())
                        .setBorder(BorderFactory.createEmptyBorder(14, 18, 14, 18));

                JLabel msg = new JLabel(
                    "<html>First paste complete.<br>" +
                    "Press <b>Enter</b> to continue or <b>Escape</b> to cancel extraction.</html>",
                    SwingConstants.CENTER);
                dialog.add(msg, BorderLayout.CENTER);

                JPanel btns = new JPanel(new FlowLayout(FlowLayout.CENTER, 10, 0));
                JButton contBtn = new JButton("Continue");
                JButton exitBtn = new JButton("Cancel");

                contBtn.addActionListener(e -> { proceed[0] = true;  dialog.dispose(); });
                exitBtn.addActionListener(e -> { proceed[0] = false; dialog.dispose(); });

                dialog.getRootPane().setDefaultButton(contBtn);
                dialog.getRootPane().registerKeyboardAction(
                    e -> { proceed[0] = false; dialog.dispose(); },
                    KeyStroke.getKeyStroke(KeyEvent.VK_ESCAPE, 0),
                    JComponent.WHEN_IN_FOCUSED_WINDOW
                );

                btns.add(contBtn);
                btns.add(exitBtn);
                dialog.add(btns, BorderLayout.SOUTH);

                dialog.pack();
                dialog.setMinimumSize(new Dimension(340, 140));
                dialog.setLocationRelativeTo(null);
                dialog.setVisible(true); // blocks EDT (modal) until disposed
            });
        } catch (Exception ignored) {}
        return proceed[0];
    }

    // -----------------------------------------------------------------------
    // Extract action
    // -----------------------------------------------------------------------

    private void runExtract() {
        if (!allPositionsSet()) {
            JOptionPane.showMessageDialog(this, "Please set all positions first.");
            return;
        }

        statusLabel.setText("Running...");
        extractCurrentButton.setEnabled(false);
        setVisible(false);

        final int stepDelay   = (int) mouseStepDelaySpinner.getValue();
        final int interval    = (int) actionIntervalSpinner.getValue();
        final int removeDelay = Math.max(700, interval);

        new Thread(() -> {
            try {
                Robot r = new Robot();
                boolean completed = runExtractCurrentSequence(r, stepDelay, interval, removeDelay, true, true);
                SwingUtilities.invokeLater(() -> {
                    statusLabel.setText(completed
                        ? "Done. Click 'Extract Current' to run again."
                        : "Extraction cancelled.");
                    extractCurrentButton.setEnabled(true);
                    setVisible(true);
                });
            } catch (AWTException ex) {
                SwingUtilities.invokeLater(() -> {
                    statusLabel.setText("Error: " + ex.getMessage());
                    extractCurrentButton.setEnabled(true);
                    setVisible(true);
                });
            }
        }).start();
    }

    /**
     * Runs the full "Extract Current" mouse/keyboard automation sequence.
     * Returns true if the sequence completed, false if the user cancelled at the mid-sequence prompt.
     * Shared building block for Extract Team and Extract League sequences.
     *
     * @param showContinuePrompt  true for standalone Extract Current (shows mid-sequence dialog);
     *                            false for automated callers like Extract Team/League.
     */
    private boolean runExtractCurrentSequence(Robot r, int stepDelay, int interval, int removeDelay,
                                              boolean showContinuePrompt, boolean clickTarget) {
        Point cur = MouseInfo.getPointerInfo().getLocation();
        int cx = cur.x, cy = cur.y;

        // ── 1. Drag + Ctrl+C the initial table ───────────────────────────────
        int[] pos = dragCopyTable(r, cx, cy, stepDelay, interval);
        cx = pos[0]; cy = pos[1];

        // ── 2. Click spreadsheet focus point, Ctrl+V ─────────────────────────
        // First iteration: click the target cell directly.
        // Subsequent iterations: the cell is already in position from the previous
        // iteration's right/up-arrow adjustment, so click the window title bar
        // instead to regain focus without disturbing the active cell.
        Point focusPoint = clickTarget ? spreadsheetTargetPos : spreadsheetWindowPos;
        smoothMouseMove(r, cx, cy, focusPoint.x, focusPoint.y, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_V);
        r.delay(interval);
        r.keyRelease(KeyEvent.VK_V);
        r.keyRelease(KeyEvent.VK_CONTROL);
        r.delay(interval);
        cx = focusPoint.x; cy = focusPoint.y;

        // ── Pause: prompt user to confirm before continuing ───────────────────
        if (showContinuePrompt && !waitForUserContinue()) {
            return false;  // end extraction sequence only; program keeps running
        }

        // ── 3–17. For each Stat Category tab ─────────────────────────────────
        for (int i = 0; i < statCategoryPos.length; i++) {
            pos = moveTo(r, cx, cy, statCategoryPos[i].x, statCategoryPos[i].y, stepDelay, interval);
            cx = pos[0]; cy = pos[1];

            copySelection(r, interval);

            pos = clickDownArrowsPaste(r, cx, cy, spreadsheetWindowPos,
                                      STAT_DOWN_ARROWS[i], stepDelay, interval);
            cx = pos[0]; cy = pos[1];
        }

        // ── After last paste: navigate to next player slot ────────────────────
        for (int i = 0; i < 7; i++) {
            r.keyPress(KeyEvent.VK_RIGHT);
            r.keyRelease(KeyEvent.VK_RIGHT);
            r.delay(50);
        }
        for (int i = 0; i < 34; i++) {
            r.keyPress(KeyEvent.VK_UP);
            r.keyRelease(KeyEvent.VK_UP);
            r.delay(50);
        }
        r.delay(interval);

        // ── 18. Remove Players ────────────────────────────────────────────────
        smoothMouseMove(r, cx, cy, removePlayersPos[0].x, removePlayersPos[0].y, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(removeDelay);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(removeDelay);

        smoothMouseMove(r, removePlayersPos[0].x, removePlayersPos[0].y,
                           removePlayersPos[1].x, removePlayersPos[1].y, 30, stepDelay);
        for (int i = 0; i < 4; i++) {
            r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
            r.delay(removeDelay);
            r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
            r.delay(removeDelay);
        }

        return true;
    }

    // -----------------------------------------------------------------------
    // Robot helper: add one player via the Select Player dropdown
    // -----------------------------------------------------------------------

    /**
     * Clicks the Select Player dropdown, navigates down by {@code downPresses} steps, and
     * presses Enter to load that player into the stats table.
     *
     * Down-press count formula (0-based original roster index I, set of indices already in table T):
     *   downPresses = I - |{t ∈ T : t < I}| + 1
     *
     * Because the site removes a player from the dropdown once they're in the table, each
     * already-added player with a lower index shifts the target up by one slot; +1 converts
     * from 0-based position to key-press count (one press lands on the first item).
     */
    private int[] addPlayerViaDropdown(Robot r, int fx, int fy, int downPresses, int stepDelay, int interval) {
        smoothMouseMove(r, fx, fy, playerSelectPos.x, playerSelectPos.y, 30, stepDelay);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(interval);
        for (int i = 0; i < downPresses; i++) {
            r.keyPress(KeyEvent.VK_DOWN);
            r.keyRelease(KeyEvent.VK_DOWN);
            r.delay(50);
        }
        r.keyPress(KeyEvent.VK_ENTER);
        r.delay(interval);
        r.keyRelease(KeyEvent.VK_ENTER);
        r.delay(interval);
        return new int[]{playerSelectPos.x, playerSelectPos.y};
    }

    // -----------------------------------------------------------------------
    // Extract Team action
    // -----------------------------------------------------------------------

    private void runExtractTeam() {
        if (!allPositionsSet() || pivotGK == null) {
            JOptionPane.showMessageDialog(this,
                "Please set all positions and select a Pivot GK before running Extract Team.");
            return;
        }

        // Build the processing roster: all players except the pivot GK, in app-defined order.
        // This order matches the website's Select Player dropdown order (pivot GK excluded
        // because they are already in the stats table and therefore absent from the dropdown).
        List<Database.Player> roster = new ArrayList<>();
        for (Database.Player p : getRosterOrder()) {
            if (p != pivotGK) roster.add(p);
        }

        if (roster.isEmpty()) {
            JOptionPane.showMessageDialog(this, "Roster has no players other than the Pivot GK.");
            return;
        }

        statusLabel.setText("Extract Team running…");
        extractCurrentButton.setEnabled(false);
        extractTeamBtn.setEnabled(false);
        setVisible(false);

        final int stepDelay   = (int) mouseStepDelaySpinner.getValue();
        final int interval    = (int) actionIntervalSpinner.getValue();
        final int removeDelay = Math.max(700, interval);
        final List<Database.Player> finalRoster = roster;

        new Thread(() -> {
            try {
                Robot r = new Robot();
                boolean success = runExtractTeamSequence(r, finalRoster, stepDelay, interval, removeDelay);
                SwingUtilities.invokeLater(() -> {
                    statusLabel.setText(success ? "Extract Team complete." : "Extract Team cancelled.");
                    refreshExtractButton();
                    setVisible(true);
                });
            } catch (AWTException ex) {
                SwingUtilities.invokeLater(() -> {
                    statusLabel.setText("Error: " + ex.getMessage());
                    refreshExtractButton();
                    setVisible(true);
                });
            }
        }).start();
    }

    /**
     * Core Extract Team automation.
     *
     * Assumptions when called:
     *   - The website's stats table contains only the pivot GK (no other players).
     *   - The Select Player dropdown lists all non-pivot-GK players in the same order as
     *     {@code roster} (which mirrors the app's roster list).
     *
     * Per-batch flow (batch size = 5 unique players):
     *   1. Add 5 players to the stats table one at a time via the Select Player dropdown.
     *      Each add is: click playerSelectPos → down N times → Enter.
     *   2. Run Extract Current sequence (no continue prompt).
     *   3. Repeat with the next 5 players.
     *
     * Last-batch padding: if fewer than 5 unique players remain, redundant players from the
     * start of the roster are appended to fill the batch to exactly 5. This ensures the site
     * always has a full table of 6 (pivot GK + 5) for a clean extraction.
     *
     * Down-press calculation: when adding a player whose 0-based original roster index is I,
     * and the set of roster indices already in the table is T:
     *   downPresses = I - |{t ∈ T : t < I}| + 1
     * Players in T that have a lower index than I were removed from the dropdown, shifting I
     * upward in the visible list; +1 converts 0-based position to key-press count.
     */
    private boolean runExtractTeamSequence(Robot r, List<Database.Player> roster,
                                           int stepDelay, int interval, int removeDelay) {
        final int BATCH_SIZE  = 5;
        final int n           = roster.size();
        final int numBatches  = (int) Math.ceil((double) n / BATCH_SIZE);

        Point cur = MouseInfo.getPointerInfo().getLocation();
        int cx = cur.x, cy = cur.y;

        for (int batch = 0; batch < numBatches; batch++) {
            int batchStart    = batch * BATCH_SIZE;
            int batchEnd      = Math.min(batchStart + BATCH_SIZE, n);
            int newCount      = batchEnd - batchStart;
            int redundantCount = BATCH_SIZE - newCount;

            // Build the ordered sequence of original roster indices to add for this batch.
            // New (unique) players come first, then redundant fill players from the roster head.
            List<Integer> toAdd = new ArrayList<>();
            for (int i = batchStart; i < batchEnd; i++) toAdd.add(i);
            for (int i = 0; i < redundantCount; i++)   toAdd.add(i);

            // Track which roster indices are currently in the stats table (cleared each batch
            // by Extract Current's Remove Players step).
            Set<Integer> inTable = new LinkedHashSet<>();

            // Add all 5 players for this batch, one dropdown interaction at a time.
            for (int idx : toAdd) {
                int countBelow = 0;
                for (int t : inTable) if (t < idx) countBelow++;
                int downPresses = idx - countBelow + 1;

                int[] pos = addPlayerViaDropdown(r, cx, cy, downPresses, stepDelay, interval);
                cx = pos[0]; cy = pos[1];
                inTable.add(idx);
            }

            // Run Extract Current (no mid-sequence continue prompt for automated batches).
            boolean completed = runExtractCurrentSequence(r, stepDelay, interval, removeDelay, false, batch == 0);
            if (!completed) return false;

            // After Extract Current, cursor ends near removePlayersPos[1].
            cx = removePlayersPos[1].x;
            cy = removePlayersPos[1].y;
        }

        return true;
    }

    // -----------------------------------------------------------------------
    // Entry point
    // -----------------------------------------------------------------------

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new USLExtractorGUI().setVisible(true));
    }
}
