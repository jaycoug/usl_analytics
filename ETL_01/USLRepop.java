import java.awt.*;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;
import java.util.Scanner;
import java.util.concurrent.TimeUnit;

public class USLRepop {

    public static void main(String[] args) {
        try {
            Scanner scanner = new Scanner(System.in);
            System.out.print("Drop downs: ");
            int downPresses = scanner.nextInt();
            scanner.close();

            Robot r = new Robot();
            int delayBetweenSteps = 5000;

            // Step 2: Move to (811, 50) and click
            r.mouseMove(811, 50);
            clickMouse(r);
            TimeUnit.MILLISECONDS.sleep(delayBetweenSteps);

            // Step 3: Press F11 (fullscreen)
            pressKey(r, KeyEvent.VK_F11);
            TimeUnit.MILLISECONDS.sleep(delayBetweenSteps);
            pressKeyMultipleTimes(r, KeyEvent.VK_UP, 2, 100);

            // Step 4: Click sequence of positions
            int[][] clickPositions = {
                {691, 125},
                {759, 385},
                {856, 385},
                {1001, 385},
                {1242, 385}
            };
            for (int[] pos : clickPositions) {
                r.mouseMove(pos[0], pos[1]);
                clickMouse(r);
                TimeUnit.MILLISECONDS.sleep(delayBetweenSteps);
            }

            // Step 5: Repeat block
            for (int i = 0; i < 5; i++) {
                r.mouseMove(1192, 313);
                clickMouse(r);
                TimeUnit.MILLISECONDS.sleep(300);

                System.out.println("Down Presses: " + downPresses);
                pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, downPresses, 80);
                r.delay(100);
                pressKey(r, KeyEvent.VK_ENTER);
                TimeUnit.MILLISECONDS.sleep(delayBetweenSteps);
            }

            // Step 6: Press F11 again (exit fullscreen)
            pressKey(r, KeyEvent.VK_F11);
            TimeUnit.MILLISECONDS.sleep(delayBetweenSteps);

            // Step 7: PgUp x7, PgDn x3, down x6
            pressKeyMultipleTimes(r, KeyEvent.VK_PAGE_UP, 7, 100);
            pressKeyMultipleTimes(r, KeyEvent.VK_PAGE_DOWN, 3, 100);
            pressKeyMultipleTimes(r, KeyEvent.VK_DOWN, 6, 100);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void clickMouse(Robot r) {
        r.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        r.delay(100);
        r.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
    }

    private static void pressKey(Robot r, int key) {
        r.keyPress(key);
        r.delay(50);
        r.keyRelease(key);
    }

    private static void pressKeyMultipleTimes(Robot r, int key, int times, int delayMs) {
        for (int i = 0; i < times; i++) {
            pressKey(r, key);
            r.delay(delayMs);
        }
    }

    private static int getCurrentX() {
        try {
            Process p = Runtime.getRuntime().exec("xdotool getmouselocation --shell");
            p.waitFor();
            Scanner s = new Scanner(p.getInputStream());
            while (s.hasNextLine()) {
                String line = s.nextLine();
                if (line.startsWith("X=")) return Integer.parseInt(line.substring(2));
            }
            s.close();
        } catch (Exception e) {
            System.out.println("Could not fetch current X. Defaulting to 0.");
        }
        return 0;
    }

    private static int getCurrentY() {
        try {
            Process p = Runtime.getRuntime().exec("xdotool getmouselocation --shell");
            p.waitFor();
            Scanner s = new Scanner(p.getInputStream());
            while (s.hasNextLine()) {
                String line = s.nextLine();
                if (line.startsWith("Y=")) return Integer.parseInt(line.substring(2));
            }
            s.close();
        } catch (Exception e) {
            System.out.println("Could not fetch current Y. Defaulting to 0.");
        }
        return 0;
    }
}

