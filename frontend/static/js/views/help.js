// Help, shortcuts and troubleshooting.
import { icon } from "../icons.js";
import { setHTML } from "../ui.js";

export async function mount(root) {
  setHTML(root, `<div class="page" style="max-width:1100px"><div class="studio no-right" style="grid-template-columns:220px minmax(0,1fr);height:auto">
    <nav class="help-toc" style="position:sticky;top:20px;align-self:start"><h4>Contents</h4>
      <a href="#/help" data-to="start">Getting started</a><a href="#/help" data-to="cutout">Cutting out subjects</a><a href="#/help" data-to="design">Designing stickers</a>
      <a href="#/help" data-to="variants">Variants</a><a href="#/help" data-to="sheet">A4 sheets &amp; printing</a><a href="#/help" data-to="cricut">Cricut workflow</a>
      <a href="#/help" data-to="keys">Keyboard shortcuts</a><a href="#/help" data-to="trouble">Troubleshooting</a><a href="#/help" data-to="privacy">Privacy &amp; limitations</a></nav>
    <div class="help-content" style="padding-left:28px">
      <h1>Help</h1>
      <section id="start"><h2>Getting started</h2><ol>
        <li>Create a project on the start page and pick a theme.</li>
        <li><b>Photos</b>: import one or more photos. Originals are copied into the project folder unchanged.</li>
        <li><b>Cut out</b>: draw a rectangle around the person and click <i>Extract subject</i>. Fix mistakes with the Keep and Remove brushes.</li>
        <li><b>Variants</b>: generate a collection, or open the <b>Editor</b> to design stickers one by one.</li>
        <li><b>A4 sheet</b>: arrange stickers in millimetres, then <b>Export</b> PNG, PDF or SVG.</li></ol>
        <p>No photos at hand? Click <i>Try a sample project</i> on the start page.</p></section>
      <section id="cutout"><h2>Cutting out subjects</h2>
        <p><b>Auto (GrabCut)</b> is classic OpenCV segmentation. It works best when the person stands out from the background. Draw a generous rectangle, extract, then paint red <i>Keep</i> marks over missed parts and blue <i>Remove</i> marks over leftover background and extract again.</p>
        <p><b>Manual</b> lets you paint the mask directly. Start from the current cut-out to touch up edges. <b>Plain bg</b> suits photos taken against a plain wall. An optional <b>local model</b> appears if you install one (see Status).</p>
        <p>Refine options: feathering softens edges, <i>Refine hair</i> uses a guided filter to follow fine strands, <i>Fill holes</i> and <i>Remove specks</i> clean the mask, and grow/shrink moves the edge. Check the result on light and dark backgrounds.</p></section>
      <section id="design"><h2>Designing stickers</h2>
        <p>The editor has a canvas in real units (rulers in mm). Add assets, text, photos and shapes from the left. Select a layer to change it on the right. With nothing selected, the right panel shows sticker settings: shape, die-cut border, outlines, shadow, background and cut offset.</p>
        <p><b>Die-cut silhouette</b> grows a border around the outline of everything on the artboard. <b>Shape</b> stickers (circle, heart, star and so on) clip the artwork to the shape. The <i>Preview</i> tab shows the finished sticker and its cut path.</p>
        <p>Photo layers always keep their proportions, so faces are never stretched. Colour treatments leave protected face regions unchanged, and you can set these regions in <i>Adjust</i>.</p></section>
      <section id="variants"><h2>Variants</h2><p>The variant generator combines your photos with crops, framings, shapes, borders, backgrounds, accessories, decorations, text and colour treatments. The same seed always gives the same result. It never generates new poses, faces or clothes. For more poses, import more photos.</p></section>
      <section id="sheet"><h2>A4 sheets &amp; printing</h2><p>A4 is 210 × 297 mm (2480 × 3508 px at 300 DPI). Set the printable area for your printer (or use the Cricut Print Then Cut preset), margins and gaps. Use automatic Grid, Pack, Fill page or Fit to page, or drag stickers by hand. Warnings flag overlaps, stickers outside the printable area and low resolution.</p>
        <p>Always print at <b>100% / Actual size</b>. “Fit to page” or “Shrink to fit” changes the sizes.</p></section>
      <section id="cricut"><h2>Cricut workflow</h2><p>For Print Then Cut, export <i>Individual PNG stickers</i>, upload each as a <i>Complex</i> image in Design Space and keep the transparent background. Choose <i>Print Then Cut</i>, check the size, then Make It. Use the SVG files when your software can use a separate cut path. Results depend on your machine and software version, so test-print first.</p></section>
      <section id="keys"><h2>Keyboard shortcuts</h2><table class="simple">
        <tr><td><kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>Z</kbd> · <kbd>Shift</kbd> <kbd>Ctrl</kbd> <kbd>Z</kbd></td><td>Undo · Redo</td></tr>
        <tr><td><kbd>Ctrl</kbd> <kbd>S</kbd></td><td>Save project</td></tr>
        <tr><td><kbd>Ctrl</kbd> <kbd>C</kbd> / <kbd>X</kbd> / <kbd>V</kbd> / <kbd>D</kbd></td><td>Copy / cut / paste / duplicate layers</td></tr>
        <tr><td><kbd>Ctrl</kbd> <kbd>G</kbd> · <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>G</kbd></td><td>Group · Ungroup</td></tr>
        <tr><td><kbd>Del</kbd> · <kbd>Esc</kbd> · <kbd>Ctrl</kbd> <kbd>A</kbd></td><td>Delete · Deselect · Select all</td></tr>
        <tr><td><kbd>[</kbd> <kbd>]</kbd> (with <kbd>Shift</kbd>: to back/front)</td><td>Layer order</td></tr>
        <tr><td>Arrow keys (with <kbd>Shift</kbd>: ×10)</td><td>Nudge</td></tr>
        <tr><td><kbd>V</kbd> · <kbd>H</kbd> / hold <kbd>Space</kbd> · <kbd>T</kbd> · <kbd>L</kbd></td><td>Select · Pan · Add text · Lock</td></tr>
        <tr><td><kbd>Ctrl</kbd> <kbd>+</kbd> / <kbd>-</kbd> / <kbd>0</kbd>, mouse wheel</td><td>Zoom in / out / fit</td></tr>
        <tr><td>Cut out: <kbd>R</kbd> <kbd>K</kbd> <kbd>X</kbd> <kbd>E</kbd> <kbd>[</kbd> <kbd>]</kbd></td><td>Rectangle, Keep, Remove, Eraser, brush size</td></tr>
        <tr><td>Sheet: <kbd>R</kbd></td><td>Rotate selected sticker 90°</td></tr></table></section>
      <section id="trouble"><h2>Troubleshooting</h2><ul>
        <li><b>The cut-out misses parts of the person:</b> paint Keep marks over them and extract again, or switch to Manual.</li>
        <li><b>A sticker comes out in several pieces:</b> keep “Join separate pieces” on, increase the border width, or move decorations so they touch.</li>
        <li><b>Low resolution warning:</b> the photo is small for the print size. Print smaller or use a larger photo.</li>
        <li><b>Printed size is wrong:</b> print at 100% / Actual size. In Design Space, set the size in mm or inches by hand.</li>
        <li><b>The app closed unexpectedly:</b> reopen the project and choose <i>Recover</i> to restore autosaved changes.</li>
        <li><b>Something else:</b> details are written to the log file shown on the Status page.</li></ul></section>
      <section id="privacy"><h2>Privacy &amp; limitations</h2><p>All processing happens on this computer. There is no cloud service, no generative AI, no telemetry and no account. Photos and metadata are never sent anywhere. Use <i>Settings → Delete all local data</i> to remove everything.</p>
        <p>Automatic segmentation is conventional computer vision and can make mistakes on busy backgrounds or fine hair. Variants are composites of your own photos and bundled graphics; they cannot create new photographic content.</p></section>
    </div></div></div>`);
  root.querySelectorAll("[data-to]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); root.querySelector(`#${a.dataset.to}`).scrollIntoView({ behavior: "smooth" }); }));
  void icon;
}
