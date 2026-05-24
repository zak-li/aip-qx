const { Client } = require('ssh2');

const conn = new Client();

conn.on('ready', () => {
  conn.exec(`
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "icn-dashboard.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "icn-app.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "g8_home_v2.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "grab_dark.svg" -exec cp /tmp/icon.svg {} \\;
    echo 'zakaria' | sudo -S find /usr/share/grafana/public -name "grab_light.svg" -exec cp /tmp/icon.svg {} \\;
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
