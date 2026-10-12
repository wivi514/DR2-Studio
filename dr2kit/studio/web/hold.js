// DR2 Studio's "Chuck holding it" view (phase 13.2): a weapon in Chuck's right hand,
// Chuck frozen in the game's idle for that kind of item, the weapon's effects playing,
// and handles to line the weapon up (dr2kit/studio/hold_view.py drives it).
//
// Python calls window.dr2 (QWebEnginePage.runJavaScript); the page answers with console
// lines that start with "dr2:" ("dr2:align {json}" when a handle was let go).
//   dr2.setChuck(url)                Chuck's parts at rest (one .glb, loaded once)
//   dr2.setPose(pose)                node name -> {rotation, translation}: the idle's first
//                                    frame (dr2kit/convert/holding.py), the rest stays
//   dr2.setWeapon(url, placement, frame, effectPoint, keepView)
//                                    the weapon .glb in its model space; placement: 16
//                                    numbers (column order) putting it in Chuck's hand;
//                                    frame: origin / axis / side / thin / length / tip /
//                                    grips in model space (the line the handles move along)
//   dr2.setEffects(list, pictures)   effects: {slot, at: 'point' | 'tip', emitters: […]};
//                                    pictures: particle picture name -> url
//   dr2.setMode(mode)                'look', 'slide', 'turn', 'length' or 'effect'
//   dr2.playClip(clip)               play a move (phase 14; dr2kit/convert/holding.py
//                                    clip: node name -> rotation / position keys, times
//                                    in seconds), looping; null: back to the still pose.
//                                    The weapon follows the right-hand prop node.
//   dr2.pauseClip(on), dr2.seekClip(fraction)   stop on a frame / go to a moment
//   dr2.setInPlace(on)               take out the move's travel (dummy01.root's straight
//                                    line from its first to its last key, on the ground)
//   dr2.setBones(on)                 draw the rig as lines (on its own for a rig that
//                                    has no model: zombies, cutscene props, cameras)
//   dr2.show(what, on)               'chuck', 'effects', 'grips'
//   dr2.resetView()
//
// The particles are a sketch of what the effect data says (dr2kit/formats/effect.py):
// each emitter's picture, its colour and size keys over the particles' life (the last
// colour time), its start box, offset, speed and gravity, drawn added together as glows
// and flames are. How many particles: count_20 (more is denser, measured in game) times a
// fixed factor; what the other fields do is not measured, so motion is approximate.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from './vendor/three/examples/jsm/controls/OrbitControls.js';
import { TransformControls } from './vendor/three/examples/jsm/controls/TransformControls.js';

const status = document.getElementById('status');
function say(text) { status.textContent = text; console.log('dr2:' + text); }
function send(kind, obj) { console.log('dr2:' + kind + ' ' + JSON.stringify(obj)); }

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
} catch (e) {
  say('no WebGL here (' + e.message + ')');
  throw e;
}
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x3a3f46);
scene.add(new THREE.HemisphereLight(0xffffff, 0x404040, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.8);
sun.position.set(1, 2, 3);
scene.add(sun);
const grid = new THREE.GridHelper(4, 16, 0x5a5f66, 0x4a4f56);
scene.add(grid);

const camera = new THREE.PerspectiveCamera(35, window.innerWidth / window.innerHeight, 0.01, 200);
camera.position.set(-1.4, 1.4, 2.2);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(-0.2, 1.0, 0.2);

// --- Chuck ----------------------------------------------------------------------------
let chuck = null;
const rest = new Map();            // bone -> {q, p} at rest
let pose = null, posed = 0;
const clean = n => THREE.PropertyBinding.sanitizeNodeName(n || '').toLowerCase();

function applyPose() {
  if (!chuck) return;
  const want = new Map();
  if (pose) for (const [name, v] of Object.entries(pose)) want.set(clean(name), v);
  let n = 0;
  for (const [bone, r] of rest) {
    // three.js renames repeated node names (each of Chuck's parts has the whole rig);
    // the glTF name stays in userData.name
    const v = want.get(clean(bone.userData.name || bone.name));
    if (v) n++;
    bone.quaternion.copy(v && v.rotation ? new THREE.Quaternion(...v.rotation) : r.q);
    bone.position.copy(v && v.translation ? new THREE.Vector3(...v.translation) : r.p);
  }
  chuck.updateMatrixWorld(true);
  posed = n;
}

// --- moves played (phase 14) ------------------------------------------------------------
// A clip's channels are sampled each frame: rotations turned the short way between keys
// (nlerp), positions in a straight line, as the toolkit reads them (formats/anim.py).
let clip = null, clipTime = 0, clipPaused = false, clipBones = null;
let handBone = null;                     // Chuck's right-hand prop node
let inPlace = true;
const ROOT = 'dummy01root';               // clean('dummy01.root'): where the body travels
const handOffset = new THREE.Matrix4();  // weapon placement relative to the hand

function sampleKeys(k, t, out, isQuat) {
  const ts = k.t, vs = k.v;
  if (ts.length === 1 || t <= ts[0]) return out.fromArray(vs[0]);
  const n = ts.length - 1;
  if (t >= ts[n]) return out.fromArray(vs[n]);
  let lo = 0, hi = n;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
  const f = (t - ts[lo]) / (ts[hi] - ts[lo]);
  const a = vs[lo], b = vs[hi];
  if (isQuat) {
    const s = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) < 0 ? -1 : 1;
    out.set(a[0] + (s * b[0] - a[0]) * f, a[1] + (s * b[1] - a[1]) * f,
            a[2] + (s * b[2] - a[2]) * f, a[3] + (s * b[3] - a[3]) * f);
    return out.normalize();
  }
  return out.set(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f);
}

function bindClip() {
  clipBones = [];
  if (!clip || !chuck) return;
  const keys = new Map();
  for (const [name, k] of Object.entries(clip.nodes)) keys.set(clean(name), k);
  for (const [bone, r] of rest) {
    const k = keys.get(clean(bone.userData.name || bone.name));
    if (k) clipBones.push([bone, k]);
  }
}

function applyClip(t) {
  if (!clipBones) bindClip();
  for (const [bone, k] of clipBones) {
    if (k.r) sampleKeys(k.r, t, bone.quaternion, true);
    if (k.p) {
      sampleKeys(k.p, t, bone.position, false);
      if (inPlace && k.p.v.length > 1 && clean(bone.userData.name || bone.name) === ROOT) {
        const a = k.p.v[0], b = k.p.v[k.p.v.length - 1];
        const f = Math.min(1, t / Math.max(clip.length, 1e-6));
        bone.position.x -= (b[0] - a[0]) * f;
        bone.position.z -= (b[2] - a[2]) * f;
      }
    }
  }
  chuck.updateMatrixWorld(true);
  followHand();
}

function findHand() {
  handBone = null;
  if (!chuck) return;
  for (const bone of rest.keys())
    if (clean(bone.userData.name || bone.name) === clean('dummy01.r_hand_prop')) { handBone = bone; break; }
}

function rememberHand() {
  // called with the still pose on: where the weapon sits relative to the hand
  if (!handBone || !weapon) return;
  chuck.updateMatrixWorld(true);
  handOffset.copy(handBone.matrixWorld).invert().multiply(holder.matrix);
}

function followHand() {
  if (!handBone || !weapon) return;
  holder.matrix.multiplyMatrices(handBone.matrixWorld, handOffset);
  holder.matrixWorldNeedsUpdate = true;
}

// --- bones as lines ---------------------------------------------------------------------
let bonesOn = false, boneLines = null;
function buildBones() {
  if (boneLines) { scene.remove(boneLines); boneLines.geometry.dispose(); boneLines = null; }
  if (!chuck || !bonesOn) return;
  const pairs = [];
  const seen = new Set();
  for (const bone of rest.keys()) {
    const key = clean(bone.userData.name || bone.name);
    if (seen.has(key)) continue;           // one copy of the rig is enough
    seen.add(key);
    if (bone.parent && bone.parent.isBone) pairs.push([bone.parent, bone]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pairs.length * 6), 3));
  boneLines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x7fd4ff, depthTest: false }));
  boneLines.renderOrder = 9;
  boneLines.frustumCulled = false;
  boneLines.userData.pairs = pairs;
  scene.add(boneLines);
}
const _v = new THREE.Vector3();
function updateBones() {
  if (!boneLines) return;
  const a = boneLines.geometry.attributes.position.array;
  boneLines.userData.pairs.forEach(([p, c], i) => {
    p.getWorldPosition(_v); a.set([_v.x, _v.y, _v.z], i * 6);
    c.getWorldPosition(_v); a.set([_v.x, _v.y, _v.z], i * 6 + 3);
  });
  boneLines.geometry.attributes.position.needsUpdate = true;
}

// --- the weapon -------------------------------------------------------------------------
// holder: the weapon's model space placed in Chuck's hand (placement from Python).
// align: the weapon's line (origin at its handle end, local y along the blade, x across
// the thin side, z across the wide side); the mesh hangs under it, so turning, sliding
// and scaling `align` does what the wizard's turn / slide / length do.
const holder = new THREE.Group();
holder.matrixAutoUpdate = false;
scene.add(holder);
const align = new THREE.Group();
holder.add(align);
const meshParent = new THREE.Group();
meshParent.matrixAutoUpdate = false;
align.add(meshParent);
const tip = new THREE.Group();
align.add(tip);
const point = new THREE.Group();         // the effect point (locator 16): +y along the blade
holder.add(point);
const grips = new THREE.Group();
holder.add(grips);
let weapon = null, frame = null, alignStart = null, pointStart = null;

function marker(colour, size) {
  const m = new THREE.Mesh(new THREE.OctahedronGeometry(size),
    new THREE.MeshBasicMaterial({ color: colour, depthTest: false, transparent: true, opacity: 0.9 }));
  m.renderOrder = 10;
  return m;
}
const pointMark = new THREE.Group();
{
  const dot = marker(0xffd21a, 0.012);
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0.25, 0)]),
    new THREE.LineBasicMaterial({ color: 0xffd21a, depthTest: false }));
  line.renderOrder = 10;
  pointMark.add(dot, line);
  point.add(pointMark);
}

function v3(a) { return new THREE.Vector3(a[0], a[1], a[2]); }

function setAlign() {
  const x = v3(frame.thin), y = v3(frame.axis), z = v3(frame.side);
  if (new THREE.Vector3().crossVectors(x, y).dot(z) < 0) z.negate();
  const basis = new THREE.Matrix4().makeBasis(x, y, z);
  align.position.copy(v3(frame.origin));
  align.quaternion.setFromRotationMatrix(basis);
  align.scale.set(1, 1, 1);
  align.updateMatrix();
  meshParent.matrix.copy(align.matrix).invert();
  tip.position.set(0, frame.length, 0);
  alignStart = { p: align.position.clone(), q: align.quaternion.clone() };
}

// --- particles --------------------------------------------------------------------------
const pictures = new Map();              // name -> THREE.Texture
const loader = new THREE.TextureLoader();
function picture(name, url) {
  if (!pictures.has(name)) {
    const t = url ? loader.load(url) : null;
    // used as stored (no sRGB conversion): the shader adds them as the game's pictures are
    pictures.set(name, t);
  }
  return pictures.get(name);
}
const dotTexture = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

const VERT = `
attribute float psize;
attribute vec4 pcolour;
varying vec4 vColour;
uniform float scale;
void main() {
  vColour = pcolour;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = psize * scale / max(-mv.z, 0.01);
  gl_Position = projectionMatrix * mv;
}`;
const FRAG = `
uniform sampler2D map;
varying vec4 vColour;
void main() {
  vec4 t = texture2D(map, vec2(gl_PointCoord.x, 1.0 - gl_PointCoord.y));
  gl_FragColor = vec4(t.rgb * vColour.rgb * t.a * vColour.a, 1.0);
}`;
const PER_COUNT = 6;                     // particles alive per unit of count_20 (a guess)

function keyAt(values, times, t) {
  const ts = [0, ...times];
  if (t <= 0) return values[0];
  for (let i = 1; i < ts.length && i < values.length; i++) {
    if (t <= ts[i]) {
      const f = (t - ts[i - 1]) / Math.max(ts[i] - ts[i - 1], 1e-6);
      const a = values[i - 1], b = values[i];
      return Array.isArray(a) ? a.map((x, k) => x + (b[k] - x) * f) : a + (b - a) * f;
    }
  }
  return values[Math.min(values.length, ts.length) - 1];
}

class Emitter {
  constructor(e, burst) {
    this.e = e;
    this.burst = burst;
    this.life = Math.max(Math.max(...e.times), 0.05);
    this.n = Math.max(4, Math.min(240, Math.round((e.count || 1) * PER_COUNT)));
    this.start = new Float32Array(this.n * 3);
    this.vel = new Float32Array(this.n * 3);
    this.birth = new Float32Array(this.n);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.n * 3), 3));
    g.setAttribute('pcolour', new THREE.BufferAttribute(new Float32Array(this.n * 4), 4));
    g.setAttribute('psize', new THREE.BufferAttribute(new Float32Array(this.n), 1));
    const mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: picture(e.texture) || dotTexture }, scale: { value: 1 } },
      vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending });
    this.points = new THREE.Points(g, mat);
    this.points.frustumCulled = false;
    for (let i = 0; i < this.n; i++) this.spawn(i, burst ? 0 : -this.life * i / this.n);
  }
  spawn(i, t) {
    const e = this.e, sv = e.shape_values || [];
    let p = [0, 0, 0];
    if ((e.shape === 1 || e.shape === 2) && sv.length === 6) {
      p = [0, 1, 2].map(k => sv[3 + k] + (sv[k] - sv[3 + k]) * Math.random());
    } else if (e.shape === 3 && sv.length) {
      const d = new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5)
        .normalize().multiplyScalar(Math.abs(sv[sv.length - 1]) * Math.random());
      p = [d.x, d.y, d.z];
    }
    for (let k = 0; k < 3; k++) {
      this.start[i * 3 + k] = p[k] + e.offset[k] + e.spread[k] * (Math.random() - 0.5);
      this.vel[i * 3 + k] = e.speed[k] * (1 + 0.3 * (Math.random() - 0.5));
    }
    this.birth[i] = t;
  }
  update(t, scale) {
    const e = this.e, g = this.points.geometry;
    const pos = g.attributes.position.array, col = g.attributes.pcolour.array,
      size = g.attributes.psize.array;
    this.points.material.uniforms.scale.value = scale;
    for (let i = 0; i < this.n; i++) {
      let age = t - this.birth[i];
      if (this.burst) {
        const period = this.life + 0.8;
        if (age > period) { this.spawn(i, this.birth[i] + period * Math.floor(age / period)); age = t - this.birth[i]; }
        if (age > this.life) { col[i * 4 + 3] = 0; size[i] = 0; continue; }
      } else if (age > this.life) {
        this.spawn(i, this.birth[i] + this.life * Math.floor(age / this.life));
        age = t - this.birth[i];
      }
      for (let k = 0; k < 3; k++)
        pos[i * 3 + k] = this.start[i * 3 + k] + this.vel[i * 3 + k] * age + 0.5 * e.gravity[k] * age * age;
      const c = keyAt(e.colours, e.times, age);
      col.set(c, i * 4);
      size[i] = 2 * keyAt(e.sizes, e.times, age);
    }
    g.attributes.position.needsUpdate = g.attributes.pcolour.needsUpdate = g.attributes.psize.needsUpdate = true;
  }
}

let emitters = [];
let showEffects = true;
function clearEffects() {
  for (const em of emitters) { em.points.parent && em.points.parent.remove(em.points); em.points.geometry.dispose(); em.points.material.dispose(); }
  emitters = [];
}

// --- handles --------------------------------------------------------------------------
const gizmo = new TransformControls(camera, renderer.domElement);
gizmo.setSize(0.8);
scene.add(gizmo.getHelper());
let mode = 'look';
gizmo.addEventListener('dragging-changed', e => {
  controls.enabled = !e.value;
  if (!e.value) finishDrag();
});
gizmo.addEventListener('objectChange', () => {
  if (mode === 'length') { const s = align.scale.y; align.scale.set(s, s, s); }
});

function setMode(m) {
  mode = m;
  gizmo.detach();
  if (!weapon || m === 'look') return;
  if (m !== 'effect' && frame && !frame.movable) {
    say('the game weapon\'s own shape stays as it is: choose a model of your own to move it');
    return;
  }
  gizmo.setSpace('local');
  gizmo.showX = gizmo.showZ = false;
  gizmo.showY = true;
  if (m === 'slide') { gizmo.setMode('translate'); gizmo.attach(align); }
  else if (m === 'turn') { gizmo.setMode('rotate'); gizmo.attach(align); }
  else if (m === 'length') { gizmo.setMode('scale'); gizmo.attach(align); }
  else if (m === 'effect') { gizmo.setMode('translate'); gizmo.attach(point); }
}

function finishDrag() {
  if (!frame) return;
  const axis = v3(frame.axis);
  if (mode === 'slide') {
    const d = align.position.clone().sub(alignStart.p).dot(axis);
    send('align', { slide: frame.slide + d });
  } else if (mode === 'turn') {
    const dq = alignStart.q.clone().invert().multiply(align.quaternion);
    const deg = THREE.MathUtils.radToDeg(2 * Math.atan2(dq.y, dq.w));
    send('align', { turn: frame.turn + deg });
  } else if (mode === 'length') {
    send('align', { length: frame.length * align.scale.y });
  } else if (mode === 'effect') {
    const d = point.position.clone().sub(pointStart).dot(axis);
    send('align', { effect_start: frame.effect_start + d });
  }
}

// --- the page's API ---------------------------------------------------------------------
function frameView() {
  const box = new THREE.Box3();
  if (chuck && chuck.visible) box.expandByObject(chuck);
  if (weapon) box.expandByObject(weapon);
  if (box.isEmpty()) return;
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  // look across the weapon's length (seen end-on it would vanish), from his front
  let d = new THREE.Vector3(0.5, 0.3, 1);
  if (frame) {
    scene.updateMatrixWorld(true);
    const axis = v3(frame.axis).transformDirection(holder.matrixWorld);
    const across = new THREE.Vector3().crossVectors(axis, new THREE.Vector3(0, 1, 0));
    if (across.length() > 0.3) {
      if (across.z < 0) across.negate();
      d = across.normalize().add(new THREE.Vector3(0, 0.35, 0.25));
    }
  }
  controls.target.copy(c);
  camera.position.copy(c).add(d.normalize().multiplyScalar(size * 1.2));
  controls.update();
}

function load(url) {
  return new Promise((ok, bad) => new GLTFLoader().load(url, ok, undefined, bad));
}

window.dr2 = {
  async setChuck(url) {
    say('loading Chuck…');
    try {
      const gltf = await load(url);
      if (chuck) scene.remove(chuck);
      chuck = gltf.scene;
      rest.clear();
      chuck.traverse(o => {
        if (o.isBone) rest.set(o, { q: o.quaternion.clone(), p: o.position.clone() });
        if (o.isMesh) { o.frustumCulled = false; for (const m of [].concat(o.material)) m.side = THREE.DoubleSide; }
      });
      scene.add(chuck);
      let meshes = 0;
      chuck.traverse(o => { if (o.isMesh) meshes++; });
      bonesOn = bonesOn || meshes === 0;
      findHand();
      applyPose();
      clipBones = null;
      buildBones();
      frameView();
      say(meshes ? `Chuck loaded, ${posed} bones posed` : `${rest.size} bones loaded`);
    } catch (err) { say('could not load Chuck: ' + (err.message || err)); }
  },
  setPose(p) { pose = p; applyPose(); rememberHand(); if (clip) applyClip(clipTime); if (chuck) say(`${posed} bones posed`); },
  playClip(c) {
    clip = c; clipTime = 0; clipBones = null;
    if (!clip) { applyPose(); if (weapon && handBone) followHand(); say('still'); return; }
    clipPaused = false;
    say(`playing ${clip.length.toFixed(2)} s (${clip.frames} frames at ${Math.round(clip.rate)}/s)`);
  },
  pauseClip(on) { clipPaused = !!on; },
  seekClip(f) { if (clip) { clipTime = Math.max(0, Math.min(1, f)) * clip.length; applyClip(clipTime); } },
  clipState() { return clip ? { time: clipTime, length: clip.length, paused: clipPaused } : null; },
  setBones(on) { bonesOn = !!on; buildBones(); },
  setInPlace(on) { inPlace = !!on; if (clip) applyClip(clipTime); },
  async setWeapon(url, placement, fr, effectPoint, keepView) {
    try {
      const gltf = await load(url);
      if (weapon) meshParent.remove(weapon);
      weapon = gltf.scene;
      weapon.traverse(o => { if (o.isMesh) for (const m of [].concat(o.material)) m.side = THREE.DoubleSide; });
      meshParent.add(weapon);
      holder.matrix.fromArray(placement);
      holder.matrixWorldNeedsUpdate = true;
      if (clip) { applyPose(); rememberHand(); applyClip(clipTime); } else rememberHand();
      frame = fr;
      setAlign();
      point.position.copy(v3(effectPoint.position));
      point.quaternion.set(...effectPoint.rotation);
      pointStart = point.position.clone();
      grips.clear();
      for (const g of fr.grips || []) { const m = marker(0xe0201a, 0.01); m.position.copy(v3(g)); grips.add(m); }
      setMode(mode);
      if (!keepView) frameView();
      say(`${fr.length.toFixed(2)} m long · slide ${fr.slide.toFixed(2)} m · turn ${Math.round(fr.turn)}°`);
    } catch (err) { say('could not load the weapon: ' + (err.message || err)); }
  },
  setEffects(list, urls) {
    clearEffects();
    for (const [name, url] of Object.entries(urls || {})) picture(name, url);
    for (const fx of list || []) {
      const parent = fx.at === 'point' ? point : tip;
      for (const e of fx.emitters) {
        const em = new Emitter(e, fx.at !== 'point');
        em.points.visible = showEffects;
        parent.add(em.points);
        emitters.push(em);
      }
    }
  },
  setMode(m) { setMode(m); },
  show(what, on) {
    if (what === 'chuck' && chuck) chuck.visible = !!on;
    if (what === 'effects') { showEffects = !!on; for (const em of emitters) em.points.visible = showEffects; }
    if (what === 'grips') { grips.visible = !!on; pointMark.visible = !!on; }
  },
  resetView() { frameView(); },
  debug() {                       // for checks: each skinned mesh, how many of its bones moved
    const out = [];
    if (chuck) chuck.traverse(o => {
      if (!o.isSkinnedMesh) return;
      let moved = 0;
      for (const b of o.skeleton.bones) { const r = rest.get(b); if (r && r.q.angleTo(b.quaternion) > 1e-3) moved++; }
      out.push(`${o.name}:${moved}/${o.skeleton.bones.length}`);
    });
    return `posed ${posed}; ` + out.join(' ');
  },
};

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
let lastTime = 0;
renderer.setAnimationLoop(() => {
  const t = clock.getElapsedTime();
  // pixels per metre at distance 1: the particles' size on screen
  const scale = renderer.domElement.height / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  for (const em of emitters) em.update(t, scale);
  const dt = Math.min(t - lastTime, 0.1);
  lastTime = t;
  if (clip && chuck) {
    if (!clipPaused) clipTime = (clipTime + dt) % Math.max(clip.length, 1e-3);
    applyClip(clipTime);
  }
  updateBones();
  controls.update();
  renderer.render(scene, camera);
});
say('ready');
