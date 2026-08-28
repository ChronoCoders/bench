// A picture of the page, taken by an engine that renders it the way a browser does.
//
// Copied from the deck's tools/shot.mjs, and it carries that file's two lessons.
// Every argument is named, because a bare http:// argument is swallowed by
// Chromium's own command line parser and the process dies before this runs. And
// the shot is taken until the same picture comes back twice: the page saying it
// is ready is not the compositor having drawn it, and a capture taken too early
// holds the layout from before the faces were swapped in, which is exactly the
// thing the vendored fonts exist to prevent.
//
// The bench measures on request, so a folder of nine tracks takes minutes to
// answer. There is no timeout here for that reason.
//
//   npx electron tools/shot.mjs --url=http://127.0.0.1:8731/?what=x --out=a.png
import { writeFileSync } from 'node:fs';
import { app, BrowserWindow } from 'electron';

const arg = (name, fallback) => {
  const found = process.argv.find(a => a.startsWith('--' + name + '='));
  return found ? found.slice(name.length + 3) : fallback;
};

const url = arg('url');
const out = arg('out');
const width = Number(arg('width', 1320));
const maxHeight = Number(arg('maxheight', 4000));

const STEADY_TRIES = 20;
const STEADY_GAP_MS = 250;

async function steady(win) {
  let previous = null;
  for (let i = 0; i < STEADY_TRIES; i++) {
    const shot = await win.webContents.capturePage();
    const bitmap = shot.toBitmap();
    if (previous && previous.equals(bitmap)) return shot;
    previous = bitmap;
    await new Promise(r => setTimeout(r, STEADY_GAP_MS));
  }
  return null;
}

app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('force-device-scale-factor', '1');

app.whenReady().then(async () => {
  if (!url || !out) {
    console.log('need --url= and --out=');
    return app.exit(2);
  }
  const win = new BrowserWindow({
    width, height: 900, show: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false }
  });
  win.setContentSize(width, 900);
  await win.loadURL(url);
  await win.webContents.executeJavaScript('document.fonts.ready.then(() => true)');
  const tall = await win.webContents.executeJavaScript(
    'Math.ceil(document.documentElement.scrollHeight)');
  win.setContentSize(width, Math.min(tall, maxHeight));
  await new Promise(r => setTimeout(r, 400));

  const shot = await steady(win);
  if (!shot) {
    console.log('the picture never stopped changing, so this would not be the page at rest');
    return app.exit(1);
  }
  writeFileSync(out, shot.toPNG());
  console.log(`${out} ${width}x${Math.min(tall, maxHeight)}`);
  app.exit(0);
});
