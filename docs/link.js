/* 폰 ↔ PC 연결 — WebRTC.
 *
 * 발표장 PC 에는 아무것도 설치할 수 없으므로, 폰이 카메라가 되고 PC 가 화면이
 * 된다. 영상은 브라우저끼리 직접(P2P) 흐르고, 서로를 찾는 신호 교환만
 * PeerJS 공개 서버를 거친다.
 *
 *   PC  : 코드를 만들어 QR 로 띄우고 기다린다
 *   폰  : QR 을 찍어 열면 코드가 주소에 담겨 있다 → 카메라를 보낸다
 *
 * 영상은 서버를 거치지 않는다. 같은 WiFi 면 공유기 안에서만 돌고, 다른 망이면
 * STUN 으로 경로를 뚫는다. 학교 WiFi 가 기기 간 통신을 막으면 폰 핫스팟에
 * PC 를 붙이면 된다.
 */
const ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";   // 헷갈리는 0·O·1·I·L 제외
const PREFIX = "shepherdron-";
const ICE = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:global.stun.twilio.com:3478" },
];

export const makeCode = (n = 6) =>
  Array.from({ length: n }, () => ALPHABET[(Math.random() * ALPHABET.length) | 0]).join("");

export const cameraUrl = (code) => {
  const u = new URL(location.href);
  u.search = ""; u.hash = "";
  u.searchParams.set("cam", code);
  return u.toString();
};

function newPeer(id) {
  return new self.Peer(id, { config: { iceServers: ICE }, debug: 0 });
}

/* ── PC : 코드를 열고 폰의 영상을 기다린다 ── */
export function hostDisplay({ onCode, onStream, onState, onStats }) {
  let peer = null, tries = 0;
  const open = () => {
    const code = makeCode();
    peer = newPeer(PREFIX + code);

    peer.on("open", () => { onCode?.(code); onState?.("waiting"); });
    peer.on("error", (e) => {
      // 코드가 이미 쓰이는 중이면 다른 코드로 다시 연다
      if (e.type === "unavailable-id" && tries++ < 5) { peer.destroy(); return open(); }
      onState?.("error", e.type === "network"
        ? "신호 서버에 연결하지 못했습니다. 인터넷을 확인하세요."
        : `연결 오류 (${e.type})`);
    });
    peer.on("call", (call) => {
      call.answer();                                   // 받기만 한다
      call.on("stream", (s) => { onState?.("live"); onStream?.(s); });
      call.on("close", () => onState?.("waiting"));
    });
    peer.on("connection", (conn) => {
      conn.on("open", () => onState?.("live"));
      conn.on("data", (d) => onStats?.(d));
      // 검출 결과를 폰으로 돌려보내 들고 있는 사람이 작동을 확인할 수 있게 한다
      hostDisplay._send = (msg) => { try { conn.send(msg); } catch (_) {} };
      conn.on("close", () => { hostDisplay._send = null; });
    });
  };
  open();
  return {
    stop() { peer?.destroy(); },
    report(msg) { hostDisplay._send?.(msg); },
  };
}

/* ── 폰 : 코드로 PC 를 찾아 카메라를 보낸다 ── */
export function joinAsCamera(code, stream, { onState, onReport }) {
  const peer = newPeer(PREFIX + makeCode(10));        // 보내는 쪽은 임의 ID
  let conn = null, call = null, retry = 0;

  const connect = () => {
    const target = PREFIX + code.toUpperCase();
    call = peer.call(target, stream);
    conn = peer.connect(target, { reliable: true });
    conn.on("open", () => { retry = 0; onState?.("live"); });
    conn.on("data", (d) => onReport?.(d));
    conn.on("close", () => onState?.("waiting"));
    call?.on("close", () => onState?.("waiting"));
  };

  peer.on("open", () => { onState?.("connecting"); connect(); });
  peer.on("error", (e) => {
    if (e.type === "peer-unavailable") {
      onState?.("error", "그 코드를 쓰는 화면을 찾지 못했습니다. PC 쪽 코드를 확인하세요.");
    } else if (e.type === "network" && retry++ < 3) {
      setTimeout(connect, 1500);
    } else {
      onState?.("error", `연결 오류 (${e.type})`);
    }
  });

  return {
    stop() { try { call?.close(); conn?.close(); } catch (_) {} peer.destroy(); },
    send(msg) { try { conn?.send(msg); } catch (_) {} },
  };
}

/* ── QR ── */
export function drawQr(el, text, cell = 5) {
  const qr = self.qrcode(0, "M");
  qr.addData(text);
  qr.make();
  el.innerHTML = qr.createSvgTag({ cellSize: cell, margin: 2, scalable: true });
  const svg = el.querySelector("svg");
  if (svg) {
    svg.removeAttribute("width"); svg.removeAttribute("height");
    svg.style.width = "100%"; svg.style.height = "auto";
    svg.querySelectorAll("rect").forEach((r) => {
      if (r.getAttribute("fill") === "#ffffff") r.setAttribute("fill", "#ffffff");
      else r.setAttribute("fill", "#0A0B0D");
    });
  }
}
