const { Client } = require('ssh2');

const conn = new Client();

conn.on('ready', () => {
  conn.exec(`
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "grafana_*.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "grafana-*.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "*logo*.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S systemctl restart grafana-server
  `, (err, stream) => {
    if (err) throw err;
    stream.on('close', () => conn.end()).on('data', (data) => {
      console.log('STDOUT: ' + data);
    }).stderr.on('data', (data) => {
      console.log('STDERR: ' + data);
    });
  });
}).connect({
  host: '10.10.10.150',
  port: 22,
  username: 'zakaria',
  password: process.env.SSH_PASSWORD || 'zakaria'
});
