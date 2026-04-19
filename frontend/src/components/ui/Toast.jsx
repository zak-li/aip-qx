import { useToastStore } from '../../store/toastStore.js';

export default function Toast() {
  const { message, type, visible } = useToastStore();

  return (
    <div className={`toast${visible ? ' show' : ''}${type ? ` ${type}` : ''}`}>
      {message}
    </div>
  );
}
