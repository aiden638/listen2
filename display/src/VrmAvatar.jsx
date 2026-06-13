import React, { useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

// Set to true to view the model from the back-side instead.
const FACE_AWAY = true;

// How far to lower the arms from the default T-pose, in radians (~77°).
// If the arms go up or cross instead, flip the sign.
const ARM_DOWN = 1.35;

// Facial expressions built from this model's morph targets (it has no VRM
// expression presets). Keys must match the backend's EMOTIONS list. Each entry
// maps morph-target names -> weight (0..1).
const EXPRESSIONS = {
  neutral: {},
  happy: { 'Facials.Eyebrow_Smile': 1, 'Facials.Eye_Smile': 0.9, 'Facials.Mouth_Smile_L': 1 },
  sad: { 'Facials.Eyebrow_Sad': 1, 'Facials.Eye_Relax': 0.3, 'Facials.Mouth_Confusion_L': 0.5, 'Facials.Mouth_Mu': 0.5, 'Facials.Eff_Tear': 0.5 },
  angry: { 'Facials.Eyebrow_Angry': 1, 'Facials.Eye_Angry': 0.8, 'Facials.Mouth_Triangle': 0.5, 'Facials.Eff_Angry': 1 },
  surprised: { 'Facials.Eyebrow_Up': 1, 'Facials.Eye_Open': 1, 'Facials.Mouth_O': 0.85 },
  relaxed: { 'Facials.Eyebrow_Relax': 1, 'Facials.Eye_Nagomi': 0.7, 'Facials.Mouth_Smile_S': 0.6 },
};
// Every morph used by any expression (so we can lerp them all toward the
// active target each frame). Eye_Blink is driven separately.
const ALL_EXPR_MORPHS = Array.from(
  new Set(Object.values(EXPRESSIONS).flatMap((o) => Object.keys(o)))
);
const BLINK_MORPH = 'Facials.Eye_Blink';
// Expressions whose eye/eyebrow shapes clash with blinking — pause blinks here.
const NO_BLINK_EXPRESSIONS = new Set(['happy', 'angry']);

// Map every morph-target name -> the meshes/indices that drive it.
function buildMorphIndex(scene) {
  const index = new Map();
  scene.traverse((o) => {
    if ((o.isMesh || o.isSkinnedMesh) && o.morphTargetDictionary && o.morphTargetInfluences) {
      for (const name in o.morphTargetDictionary) {
        const i = o.morphTargetDictionary[name];
        if (!index.has(name)) index.set(name, []);
        index.get(name).push({ influences: o.morphTargetInfluences, i });
      }
    }
  });
  return index;
}

function applyMorph(index, name, value) {
  const targets = index.get(name);
  if (!targets) return;
  for (const t of targets) t.influences[t.i] = value;
}

// Occasional quick blink (returns 0..1), every ~4.5s.
function blinkAmount(t) {
  const period = 4.5;
  const local = t % period;
  const dur = 0.12;
  if (local > dur) return 0;
  return Math.sin((local / dur) * Math.PI);
}

// Loads a .vrm and frames the camera on the upper body using reliable bone
// positions (NOT the bounding box, which is unreliable for skinned meshes).
// The camera is re-applied every frame so nothing can reset it.
function VrmModel({ url, expression = 'neutral', onError }) {
  const { camera } = useThree();
  const [vrm, setVrm] = useState(null);
  // Camera framing computed once from the head/hips bones: where to look
  // (x,y,z) and how far back to sit (dist).
  const frameRef = useRef(null);
  const tRef = useRef(0);
  const morphIndexRef = useRef(null);   // morph name -> drivers
  const curWeightsRef = useRef({});     // smoothed current expression weights
  const exprRef = useRef('neutral');
  exprRef.current = expression;

  useEffect(() => {
    let disposed = false;
    let loaded = null;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    loader.load(
      url,
      (gltf) => {
        if (disposed) return;
        const model = gltf.userData.vrm;
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        model.scene.rotation.y = FACE_AWAY ? 0 : Math.PI;
        model.scene.updateMatrixWorld(true);
        model.scene.traverse((o) => { o.frustumCulled = false; });
        const fixedMats = flattenToUnlit(model.scene);
        cleanupAccessories(model.scene);

        // Use the actual bone world positions to frame the upper body.
        const head = model.humanoid?.getNormalizedBoneNode('head');
        const hips = model.humanoid?.getNormalizedBoneNode('hips');
        const headPos = new THREE.Vector3();
        const hipsPos = new THREE.Vector3();
        let targetX = 0, targetZ = 0, topY, botY;
        if (head && hips) {
          head.getWorldPosition(headPos);
          hips.getWorldPosition(hipsPos);
          const span = Math.max(headPos.y - hipsPos.y, 0.1);
          topY = headPos.y + span * 0.6;    // headroom above the head (hair top)
          botY = hipsPos.y + span * 0.05;    // just above the hips
          targetX = headPos.x;               // aim at the model's real x/z
          targetZ = headPos.z;
        } else {
          // Fallback to bounding box if bones are missing.
          const box = new THREE.Box3().setFromObject(model.scene);
          topY = box.max.y;
          botY = box.max.y - (box.max.y - box.min.y) * 0.42;
          const c = new THREE.Vector3();
          box.getCenter(c);
          targetX = c.x; targetZ = c.z;
        }

        const targetY = (topY + botY) / 2;
        const extent = (topY - botY) * 1.1;
        const fovRad = (camera.fov * Math.PI) / 180;
        const dist = extent / 2 / Math.tan(fovRad / 2);

        frameRef.current = { x: targetX, y: targetY, z: targetZ, dist };

        camera.near = Math.max(dist / 100, 0.01);
        camera.far = dist * 100 + 10;
        camera.updateProjectionMatrix();

        // Pose: lower the arms from the default T-pose.
        const poseArm = (name, z) => {
          const b = model.humanoid?.getNormalizedBoneNode(name);
          if (b) b.rotation.z = z;
        };
        poseArm('leftUpperArm', -ARM_DOWN);
        poseArm('rightUpperArm', ARM_DOWN);
        // Bake the pose and let the spring bones (hair/skirt) settle.
        for (let i = 0; i < 60; i++) model.update(1 / 60);

        // Index the face morph targets so we can drive expressions/blinks.
        morphIndexRef.current = buildMorphIndex(model.scene);

        console.log('[VrmAvatar] ready. target=',
          [targetX, targetY, targetZ].map((n) => n.toFixed(2)),
          'dist=', dist.toFixed(3), 'meshes=', countMeshes(model.scene),
          'unlitConverted=', fixedMats);

        loaded = model;
        setVrm(model);
      },
      undefined,
      (err) => { console.error('[VrmAvatar] load failed:', err); onError?.(err); }
    );
    return () => {
      disposed = true;
      if (loaded) VRMUtils.deepDispose(loaded.scene);
    };
  }, [url]);

  useFrame((_, delta) => {
    if (!vrm) return;

    // Keep the camera locked on the framed target every frame.
    const f = frameRef.current;
    if (f) {
      camera.position.set(f.x, f.y, f.z + f.dist);
      camera.lookAt(f.x, f.y, f.z);
    }

    // Subtle "alive" idle: gentle head/spine sway.
    tRef.current += delta;
    const t = tRef.current;
    const spine = vrm.humanoid?.getNormalizedBoneNode('spine');
    if (spine) spine.rotation.x = Math.sin(t * 1.2) * 0.02;
    const head = vrm.humanoid?.getNormalizedBoneNode('head');
    if (head) {
      head.rotation.y = Math.sin(t * 0.6) * 0.05;
      head.rotation.x = Math.sin(t * 0.9) * 0.02;
    }

    // Apply humanoid pose + spring bones first (this model has no VRM
    // expression presets, so it won't touch our morph targets below).
    vrm.update(delta);

    // Drive the facial expression via morph targets, easing toward the target.
    const idx = morphIndexRef.current;
    if (idx) {
      const target = EXPRESSIONS[exprRef.current] || EXPRESSIONS.neutral;
      const cur = curWeightsRef.current;
      const ease = Math.min(1, delta * 8);
      for (const name of ALL_EXPR_MORPHS) {
        const desired = target[name] || 0;
        const next = (cur[name] ?? 0) + (desired - (cur[name] ?? 0)) * ease;
        cur[name] = next;
        applyMorph(idx, name, next);
      }
      // Blinking, layered on top — paused for expressions that clash with it.
      const blink = NO_BLINK_EXPRESSIONS.has(exprRef.current) ? 0 : blinkAmount(t);
      applyMorph(idx, BLINK_MORPH, blink);
    }
  });

  if (!vrm) return null;
  return <primitive object={vrm.scene} />;
}

// This VRM was exported with all the VRChat toggle items ON by default, so the
// glasses, mask, and several alternate outfits (roomwear/swimwear/towel) all
// render at once — stacked into a blotchy mess — plus toon "_Outline" shells
// that duplicate over the body once flattened to unlit. Hide the optional
// "Other_Mesh" layer + every outline shell, and switch the backpack off, so
// only the base school uniform, body, face and hair remain.
function cleanupAccessories(root) {
  let hidden = 0, morphed = 0;
  const offMorphs = ['Shape_Acc.Backpack_OFF', 'Shape_Acc_Outline.Backpack_OFF'];
  root.traverse((o) => {
    if (o.name === 'Other_Mesh' || /_Outline$/.test(o.name)) {
      o.visible = false;
      hidden++;
    }
    if ((o.isMesh || o.isSkinnedMesh) && o.morphTargetDictionary) {
      offMorphs.forEach((name) => {
        const i = o.morphTargetDictionary[name];
        if (i !== undefined) { o.morphTargetInfluences[i] = 1; morphed++; }
      });
    }
  });
  console.log('[VrmAvatar] cleanup: hidden=', hidden, 'morphsOff=', morphed);
}

function countMeshes(root) {
  let n = 0;
  root.traverse((o) => { if (o.isMesh || o.isSkinnedMesh) n++; });
  return n;
}

// The model's materials render large areas black (shading / shade-color /
// normal issues, regardless of shader type). Convert every material to an
// unlit MeshBasicMaterial that just shows its base color texture at full
// brightness — independent of light direction, so nothing turns black.
function flattenToUnlit(root) {
  const info = [];
  let converted = 0;
  root.traverse((o) => {
    if (!o.isMesh && !o.isSkinnedMesh) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const out = mats.map((m) => {
      if (!m) return m;
      info.push({
        name: m.name, type: m.type, mtoon: !!m.isMToonMaterial,
        map: !!m.map, color: m.color?.getHexString?.() ?? null,
      });
      if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
      const basic = new THREE.MeshBasicMaterial({
        map: m.map || null,
        // If there's a texture, show it at full strength (white tint); only
        // fall back to the material colour when there's no texture.
        color: m.map ? 0xffffff : (m.color ? m.color.clone() : new THREE.Color(0xffffff)),
        transparent: !!m.transparent,
        opacity: m.opacity != null ? m.opacity : 1,
        alphaTest: m.alphaTest || 0,
        alphaMap: m.alphaMap || null,
        side: m.side != null ? m.side : THREE.FrontSide,
        depthWrite: m.depthWrite != null ? m.depthWrite : true,
        vertexColors: false,
      });

      // The "black patch" over the face was the toon outline material baked
      // onto the face mesh (an inverted hull) covering it. Hide every outline
      // material; leave the real face layers (skin, eyes, iris, brows, mouth)
      // opaque so they render with correct depth and stay visible.
      const nm = m.name || '';
      if (/Outline/i.test(nm)) {
        basic.colorWrite = false;   // toon outline shell -> render nothing
        basic.depthWrite = false;
      }

      converted++;
      return basic;
    });
    o.material = Array.isArray(o.material) ? out : out[0];
  });
  console.log('[VrmAvatar] materials:', JSON.stringify(info));
  return converted;
}

// 3D avatar widget. Rounded canvas with a subtle backdrop to match styling.
export default function VrmAvatar({ url = '/Hayakawa_Aoi.vrm', expression = 'neutral', onError }) {
  return (
    <Canvas
      style={{ width: '100%', height: '100%', borderRadius: '16px' }}
      gl={{ alpha: true, antialias: true }}
      camera={{ position: [0, 1.3, 1.0], fov: 22 }}
    >
      {/* Transparent background (canvas uses alpha) so the avatar sits
          directly on the page. The avatar uses unlit materials, so no scene
          lights are needed — its colours come straight from the textures. */}
      <VrmModel url={url} expression={expression} onError={onError} />
    </Canvas>
  );
}
