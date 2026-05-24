const { Client } = require('ssh2');
const fs = require('fs');

const conn = new Client();
const localIconPath = 'd:\\\\WWW\\\\regx\\\\assets\\\\vector\\\\icon.svg';

conn.on('ready', () => {
  console.log('Client :: ready');
  conn.sftp((err, sftp) => {
    if (err) throw err;
    console.log('SFTP :: ready');
    const readStream = fs.createReadStream(localIconPath);
    const writeStream = sftp.createWriteStream('/tmp/icon.svg');
    
    writeStream.on('close', () => {
      console.log('File transferred successfully');
      
      const commands = `
        echo 'zakaria' | sudo -S cp /tmp/icon.svg /usr/share/grafana/public/img/grafana_icon.svg
        echo 'zakaria' | sudo -S cp /tmp/icon.svg /usr/share/grafana/public/img/grafana_com_auth_icon.svg
        echo 'zakaria' | sudo -S convert -background none -resize 32x32 /tmp/icon.svg /usr/share/grafana/public/img/fav32.png
        echo 'zakaria' | sudo -S convert -background none -resize 152x152 /tmp/icon.svg /usr/share/grafana/public/img/apple-touch-icon.png
        echo 'zakaria' | sudo -S systemctl restart grafana-server
      `;
      
      conn.exec(commands, (err, stream) => {
        if (err) throw err;
        stream.on('close', (code, signal) => {
          console.log('Commands executed. Code:', code);
          conn.end();
        }).on('data', (data) => {
          console.log('STDOUT: ' + data);
        }).stderr.on('data', (data) => {
          console.log('STDERR: ' + data);
        });
      });
    });
    
    readStream.pipe(writeStream);
  });
}).connect({
  host: '10.10.10.150',
  port: 22,
  username: 'zakaria',
  password: process.env.SSH_PASSWORD || 'zakaria'
});
