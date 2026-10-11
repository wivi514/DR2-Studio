// Level materials in DR2 Studio's 3D views (viewer.js, maps.js): lightmaps and
// two-texture blends, drawn as the game's level shaders draw them.
//
// What the .glb carries (dr2kit/convert/gltf.py, lightmap_slots and blend_slots):
// * a lightmap (LM_* / AO_*: baked light) as the occlusion texture on its UV set, with
//   extras.dr2.lightmap naming it;
// * a blend in extras.dr2.blend: the overlay texture and UV set, and either a mask
//   texture (blend by its green channel, squared: CM2DDU…) or "overlay.a" (by the
//   overlay's alpha: CM2DDX…).
// The shaders (docs/formats.md §Levels) compute, in linear light,
//     mix(base², overlay², k) × lightmap²
// "²" is their gamma: three.js reads these textures as sRGB, which is close.
// MeshBasicMaterial with a lightMap gives colour × lightMap × intensity / π, so
// intensity π; the scene's lights don't touch lightmapped surfaces (the lightmap is
// their light), as in the game. three.js only names four UV sets (uv … uv3): a lightmap
// on a 5th or 6th set is copied onto uv3, which these materials don't use otherwise.
import * as THREE from 'three';

function channelOf(geo, ch) {
  if (ch <= 3) return ch;
  const a = geo.getAttribute('texcoord_' + ch);
  if (a) geo.setAttribute('uv3', a);
  return 3;
}

function withChannel(tex, ch, srgb) {
  const t = tex.clone();
  t.channel = ch;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.needsUpdate = true;
  return t;
}

export async function applyLevelMaterials(gltf) {
  const parser = gltf.parser;
  const json = parser.json;
  let n = 0;
  const jobs = [];
  gltf.scene.traverse(o => { if (o.isMesh) jobs.push(o); });
  for (const o of jobs) {
    const mats = [].concat(o.material);
    const out = [];
    for (const m of mats) {
      const assoc = parser.associations.get(m);
      const def = assoc && assoc.materials !== undefined ? json.materials[assoc.materials] : null;
      const dr2 = (def && def.extras && def.extras.dr2) || {};
      if (!dr2.lightmap && !dr2.blend) { out.push(m); continue; }
      const b = new THREE.MeshBasicMaterial({
        name: m.name, map: m.map, color: m.color, transparent: m.transparent,
        opacity: m.opacity, alphaTest: m.alphaTest, side: m.side,
      });
      b.userData = m.userData;
      const only = window.dr2LevelDebug;        // 'colour' or 'light': one half only
      if (only === 'light') b.map = null;
      if (dr2.lightmap && m.aoMap && only !== 'colour') {
        b.lightMap = withChannel(m.aoMap, channelOf(o.geometry, m.aoMap.channel), true);
        b.lightMapIntensity = Math.PI;
      }
      const bl = dr2.blend;
      if (bl && m.map && !only) {
        const over = await parser.getDependency('texture', bl.overlay);
        b.specularMap = withChannel(over, bl.overlay_uv, true);           // the overlay
        let k = 'overT.a';
        if (bl.mask !== null && bl.mask !== undefined) {
          const mask = await parser.getDependency('texture', bl.mask);
          b.alphaMap = withChannel(mask, bl.mask_uv, true);                // the mask
          k = 'texture2D( alphaMap, vAlphaMapUv ).g';
        }
        b.onBeforeCompile = sh => {
          sh.fragmentShader = sh.fragmentShader
            .replace('#include <map_fragment>',
              `#ifdef USE_MAP
                vec4 baseT = texture2D( map, vMapUv );
                vec4 overT = texture2D( specularMap, vSpecularMapUv );
                float k = clamp( ${k}, 0.0, 1.0 );
                diffuseColor *= vec4( mix( baseT.rgb, overT.rgb, k ), baseT.a );
              #endif`)
            .replace('#include <alphamap_fragment>', '')
            .replace('#include <specularmap_fragment>', 'float specularStrength = 1.0;');
        };
        b.customProgramCacheKey = () => 'dr2blend-' + k;
      }
      m.dispose();
      out.push(b);
      n++;
    }
    o.material = Array.isArray(o.material) ? out : out[0];
  }
  return n;
}
