import { expect, test } from "@playwright/test";

const JD_TEXT = `岗位：后端开发实习生
职责：
1. 参与业务后台接口开发与维护。
2. 配合完成数据库设计、性能优化与问题排查。
3. 参与微服务架构下的模块开发和单元测试。
要求：
1. 熟悉 Java，了解 Spring Boot。
2. 熟悉 MySQL，了解索引和 SQL 优化。
3. 了解 Redis、消息队列，有 Linux 使用经验。`;

test("frontend backend chain stays healthy", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("session-panel")).toBeVisible();
  await expect(page.getByTestId("memory-panel")).toBeVisible();
  await expect(page.getByTestId("chat-panel")).toBeVisible();
  await expect(page.getByTestId("jd-tool-panel")).toBeVisible();

  await page.getByTestId("chat-input").fill("我在准备后端开发实习，请帮我梳理一周复习重点。");
  await page.getByTestId("chat-send").click();

  await expect(page.getByText("已基于当前输入生成求职建议。")).toBeVisible({
    timeout: 15000,
  });

  await expect(page.getByTestId("memory-panel")).toContainText("可信度", {
    timeout: 15000,
  });

  await page.getByTestId("jd-input").fill(JD_TEXT);
  await page.getByTestId("jd-analyze").click();

  await expect(
    page.getByText("这是一个以后端开发实习为目标的岗位，强调接口开发、数据库优化和基础中间件能力。"),
  ).toBeVisible({ timeout: 15000 });

  await expect(page.getByText("Spring Boot 接口开发")).toBeVisible();
  await expect(page.getByText("消息队列使用场景")).toBeVisible();
});
