const sharp = require('sharp');
const path = require('path');
const files = [
  ['assets/icon-v5-fusion.svg', 512, '_icon-v5-fusion_512.png'],
  ['assets/icon-v5-fusion.svg', 64,  '_icon-v5-fusion_64.png'],
  ['assets/icon-v5-fusion-web.svg', 512, '_icon-v5-fusion-web_512.png'],
  ['assets/icon-v5-fusion-web.svg', 64,  '_icon-v5-fusion-web_64.png'],
];
(async () => {
  for (const [svg, size, out] of files) {
    await sharp(path.join(process.cwd(), svg), { density: 384 })
      .resize(size, size)
      .png()
      .toFile(path.join(process.cwd(), out));
    console.log('rendered', out);
  }
})().catch(e => { console.error(e); process.exit(1); });
