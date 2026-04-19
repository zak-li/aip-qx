import '@lottiefiles/lottie-player';

export default function Welcome() {
  return (
    <div className="welcome">
      <lottie-player
        src="/animations/Animation5.json"
        background="transparent"
        speed="0.7"
        style={{ width: '420px', height: '420px' }}
        loop
        autoplay
      />
      <div className="welcome-title">HET X // RAG Intelligence Terminal</div>
      <div className="welcome-sub">
        Connected to real-time blockchain platform data. Query assets,
        compliance records, transactions and Hyperledger Fabric architecture.
      </div>
    </div>
  );
}
