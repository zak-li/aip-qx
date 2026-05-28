const { Client } = require('ssh2');

const conn = new Client();

conn.on('ready', () => {
  conn.exec(`
    echo 'zakaria' | sudo -S sed -i 's/\\[\\[.AppTitle\\]\\]/Pex/g' /usr/share/grafana/public/views/index.html
    echo 'zakaria' | sudo -S sed -i 's/Grafana/Pex/g' /usr/share/grafana/public/views/index.html
    echo 'zakaria' | sudo -S sed -i 's/Grafana/Pex/g' /usr/share/grafana/public/build/app*.js
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
