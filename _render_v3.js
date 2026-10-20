const sharp = require('sharp');
const fs = require('fs');
const files = ['assets/icon-v3-approach.svg','assets/icon-v3-approach-web.svg'];
(async () => {
  for (const f of files) {
    const svg = fs.readFileSync(f);
    const base = f.split('/').pop().replace('.svg','');
    await sharp(svg, { density: 384 }).resize(512,512).png().toFile(`_${base}_512.png`);
    await sharp(svg, { density: 64 }).resize(64,64).png().toFile(`_${base}_64.png`);
    console.log('rendered', base);
  }
})();
