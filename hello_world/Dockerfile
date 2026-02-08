FROM node:22-alpine

WORKDIR /app

COPY package*.json /app

RUN npm install

COPY . .

EXPOSE 8002

CMD ["node", "hello_world.ts"]

