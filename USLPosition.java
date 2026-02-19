import java.awt.AWTException;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;

public class USLPosition {

    public USLPosition() throws AWTException, InterruptedException {
        Robot ro = new Robot();

        // 1. Slowly move to (811, 50), then click
        smoothMouseMove(ro, getCurrentX(), getCurrentY(), 811, 50, 50);
        clickMouse(ro);

        // 2. Press Page Up 7x, then Page Down 3x, then down 6x
        pressKeyMultipleTimes(ro, KeyEvent.VK_PAGE_UP, 7, 100);
        pressKeyMultipleTimes(ro, KeyEvent.VK_PAGE_DOWN, 3, 300);
        pressKeyMultipleTimes(ro, KeyEvent.VK_DOWN, 6, 100);

        // 3. Move to (1727, 50), then click
        smoothMouseMove(ro, 811, 50, 1727, 50, 50);
        clickMouse(ro);
    }

    public static void main(String[] args) {
        try {
            new USLPosition();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void clickMouse(Robot r) {
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(100);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
    }

    private void pressKeyMultipleTimes(Robot r, int key, int times, int delayMs) {
        for (int i = 0; i < times; i++) {
            r.keyPress(key);
            r.delay(50);
            r.keyRelease(key);
            r.delay(delayMs);
        }
    }

    private void smoothMouseMove(Robot r, int startX, int startY, int endX, int endY, int steps) {
        double dx = (endX - startX) / (double) steps;
        double dy = (endY - startY) / (double) steps;

        for (int i = 0; i <= steps; i++) {
            int x = (int) (startX + dx * i);
            int y = (int) (startY + dy * i);
            r.mouseMove(x, y);
            r.delay(10);
        }
    }

    private int getCurrentX() {
        try {
            Process p = Runtime.getRuntime().exec("xdotool getmouselocation --shell");
            p.waitFor();
            java.util.Scanner s = new java.util.Scanner(p.getInputStream());
            while (s.hasNextLine()) {
                String line = s.nextLine();
                if (line.startsWith("X=")) return Integer.parseInt(line.substring(2));
            }
            s.close();
        } catch (Exception e) {
            System.out.println("Could not fetch current X position. Defaulting to 0.");
        }
        return 0;
    }

    private int getCurrentY() {
        try {
            Process p = Runtime.getRuntime().exec("xdotool getmouselocation --shell");
            p.waitFor();
            java.util.Scanner s = new java.util.Scanner(p.getInputStream());
            while (s.hasNextLine()) {
                String line = s.nextLine();
                if (line.startsWith("Y=")) return Integer.parseInt(line.substring(2));
            }
            s.close();
        } catch (Exception e) {
            System.out.println("Could not fetch current Y position. Defaulting to 0.");
        }
        return 0;
    }
}

