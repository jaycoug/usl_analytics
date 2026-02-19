import java.awt.AWTException;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;
import java.util.concurrent.TimeUnit;

public class USLCollect {

    public static void main(String[] args) {
        try {
            Robot r = new Robot();
            
            // Step 1: Player names with first click-and-drag (remaining by Action1)
            smoothMouseMove(r, getCurrentX(r), getCurrentY(r), 104, 287, 30);
            r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
            TimeUnit.MILLISECONDS.sleep(15);
            smoothMouseMove(r, 111, 287, 123, 287, 10);
            r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
            TimeUnit.MILLISECONDS.sleep(15);
            r.keyPress(KeyEvent.VK_CONTROL);
            r.keyPress(KeyEvent.VK_C);
            r.delay(15);
            r.keyRelease(KeyEvent.VK_C);
            r.keyRelease(KeyEvent.VK_CONTROL);

            // Step 2
            pasteAt(r, 1727, 50);
            delay();

            // Step 3
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 6, 100);
            delay();

            // Step 4
            smoothClick(r, 227, 230);
            delay();

            // Step 5: Action 1
            performAction1(r);
            delay();

            // Step 6
            pasteAt(r, 1727, 50);
            delay();

            // Step 7
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 4, 100);
            delay();

            // Step 8
            smoothClick(r, 303, 230);
            delay();

            // Step 9: Action 1
            performAction1(r);
            delay();

            // Step 10
            pasteAt(r, 1727, 50);
            delay();

            // Step 11
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 11, 100);
            delay();

            // Step 12
            smoothClick(r, 362, 230);
            delay();

            // Step 13: Action 1
            performAction1(r);
            delay();

            // Step 14
            pasteAt(r, 1727, 50);
            delay();

            // Step 15
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 5, 100);
            delay();

            // Step 16
            smoothClick(r, 440, 230);
            delay();

            // Step 17: Action 1
            performAction1(r);
            delay();

            // Step 18
            pasteAt(r, 1727, 50);
            delay();

            // Step 19
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 4, 100);
            delay();

            // Step 20
            smoothClick(r, 525, 230);
            delay();

            // Step 21: Action 1
            performAction1(r);
            delay();

            // Step 22
            pasteAt(r, 1727, 50);
            delay();

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void performAction1(Robot r) throws InterruptedException {
        int copyLevel = 370;
        // Move to (104, y=copyLevel), click and hold
        smoothMouseMove(r, getCurrentX(r), getCurrentY(r), 104, copyLevel, 30);
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        TimeUnit.MILLISECONDS.sleep(15);

        // Drag to (123, y=copyLevel), then release
        smoothMouseMove(r, 111, copyLevel, 123, copyLevel, 10);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        TimeUnit.MILLISECONDS.sleep(15);

        // Press Ctrl+C
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_C);
        r.delay(15);
        r.keyRelease(KeyEvent.VK_C);
        r.keyRelease(KeyEvent.VK_CONTROL);
    }

    private static void pasteAt(Robot r, int x, int y) throws InterruptedException {
        smoothMouseMove(r, getCurrentX(r), getCurrentY(r), x, y, 30);
        clickMouse(r);

        // Press Ctrl+V
        r.keyPress(KeyEvent.VK_CONTROL);
        r.keyPress(KeyEvent.VK_V);
        r.delay(15);
        r.keyRelease(KeyEvent.VK_V);
        r.keyRelease(KeyEvent.VK_CONTROL);
    }

    private static void smoothClick(Robot r, int x, int y) throws InterruptedException {
        smoothMouseMove(r, getCurrentX(r), getCurrentY(r), x, y, 30);
        clickMouse(r);
    }

    private static void clickMouse(Robot r) {
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(15);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
    }

    private static void pressKeyMultipleTimes(Robot r, int key, int times, int delayMs) {
        for (int i = 0; i < times; i++) {
            r.keyPress(key);
            r.delay(15);
            r.keyRelease(key);
            r.delay(delayMs);
        }
    }

    private static void smoothMouseMove(Robot r, int startX, int startY, int endX, int endY, int steps) {
        double dx = (endX - startX) / (double) steps;
        double dy = (endY - startY) / (double) steps;

        for (int i = 0; i <= steps; i++) {
            int x = (int) (startX + dx * i);
            int y = (int) (startY + dy * i);
            r.mouseMove(x, y);
            r.delay(10);
        }
    }

    private static int getCurrentX(Robot r) {
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
            System.out.println("Defaulting current X to 0");
        }
        return 0;
    }

    private static int getCurrentY(Robot r) {
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
            System.out.println("Defaulting current Y to 0");
        }
        return 0;
    }

    private static void delay() throws InterruptedException {
        TimeUnit.SECONDS.sleep(1);
    }
}

