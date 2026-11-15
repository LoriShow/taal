FROM nginx:1.27-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY site/index.html site/styles.css site/app.js site/config.js /usr/share/nginx/html/
