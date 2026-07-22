"""
╔══════════════════════════════════════════════════════════════════════════╗
║  ROSETTA WAVES 41-45 — HYPERSCALE EXPANSION (ROAD TO 200 CONCEPTS)       ║
║  dockerfile_syntax | kubernetes_deployment | terraform_hcl |            ║
║  ansible_hcl | github_actions_yaml | gitlab_ci_yaml | jenkins_yaml |    ║
║  circleci_yaml | makefile_syntax | cmake_lists | meson_build |          ║
║  bazel_build | ninja_build | gradle_xml | maven_groovy | ant_xml |      ║
║  npm_package_json | yarn_lock | cargo_toml | gemfile_ruby |            ║
║  requirements_txt | pipfile_python | pyproject_toml | go_mod |          ║
║  composer_json | mix_exs | rebar_config | package_swift | podfile      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

EXPANDED_V41_45 = {}

# WAVE 41: DevOps & Infrastructure as Code (Conceptual, focusing on common configs)
EXPANDED_V41_45["dockerfile_syntax"] = {
    "Python": "# Dockerfile\nFROM python:3.9-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nCMD [\"python\", \"main.py\"]",
    "Node.js": "FROM node:18-alpine\nWORKDIR /usr/src/app\nCOPY package*.json ./\nRUN npm install --only=production\nCOPY . .\nEXPOSE 8080\nCMD [ \"node\", \"server.js\" ]",
    "Go": "# Multi-stage build\nFROM golang:1.20 AS builder\nWORKDIR /app\nCOPY . .\nRUN go build -o main .\n\nFROM alpine:latest\nWORKDIR /app\nCOPY --from=builder /app/main .\nCMD [\"./main\"]",
    "Rust": "FROM rust:1.70 as builder\nWORKDIR /usr/src/myapp\nCOPY . .\nRUN cargo install --path .\n\nFROM debian:bullseye-slim\nCOPY --from=builder /usr/local/cargo/bin/myapp /usr/local/bin/myapp\nCMD [\"myapp\"]",
    "Java": "FROM eclipse-temurin:17-jdk-alpine as build\nWORKDIR /app\nCOPY . .\nRUN ./gradlew build\n\nFROM eclipse-temurin:17-jre-alpine\nCOPY --from=build /app/build/libs/app.jar app.jar\nENTRYPOINT [\"java\",\"-jar\",\"/app.jar\"]"
}

EXPANDED_V41_45["kubernetes_deployment"] = {
    "YAML": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: my-app\nspec:\n  replicas: 3\n  selector:\n    matchLabels:\n      app: my-app\n  template:\n    metadata:\n      labels:\n        app: my-app\n    spec:\n      containers:\n      - name: my-app\n        image: my-app:1.0.0\n        ports:\n        - containerPort: 8080\n        env:\n        - name: DB_HOST\n          valueFrom:\n            secretKeyRef:\n              name: db-secret\n              key: host"
}

EXPANDED_V41_45["terraform_hcl"] = {
    "HCL": "provider \"aws\" {\n  region = \"us-west-2\"\n}\n\nresource \"aws_instance\" \"web\" {\n  ami           = \"ami-0c55b159cbfafe1f0\"\n  instance_type = \"t2.micro\"\n\n  tags = {\n    Name = \"HelloWorld\"\n  }\n}\n\noutput \"public_ip\" {\n  value = aws_instance.web.public_ip\n}"
}

EXPANDED_V41_45["github_actions_yaml"] = {
    "YAML": "name: CI\non:\n  push:\n    branches: [ main ]\n  pull_request:\n    branches: [ main ]\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n    - uses: actions/checkout@v3\n    - name: Set up Python 3.10\n      uses: actions/setup-python@v4\n      with:\n        python-version: \"3.10\"\n    - name: Install dependencies\n      run: pip install -r requirements.txt\n    - name: Run tests\n      run: pytest"
}

# WAVE 42: Build Systems
EXPANDED_V41_45["makefile_syntax"] = {
    "Make": "CC=gcc\nCFLAGS=-I.\nDEPS = hellomake.h\nOBJ = hellomake.o hellofunc.o\n\n%.o: %.c $(DEPS)\n\t$(CC) -c -o $@ $< $(CFLAGS)\n\nhellomake: $(OBJ)\n\t$(CC) -o $@ $^ $(CFLAGS)\n\n.PHONY: clean\nclean:\n\trm -f *.o hellomake"
}

EXPANDED_V41_45["cmake_lists"] = {
    "CMake": "cmake_minimum_required(VERSION 3.10)\nproject(HelloWorld)\n\nset(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED True)\n\nadd_executable(HelloWorld main.cpp)\n\n# target_link_libraries(HelloWorld mylib)"
}

EXPANDED_V41_45["gradle_xml"] = {
    "Groovy": "plugins {\n    id 'java'\n    id 'org.springframework.boot' version '3.0.0'\n}\n\ngroup = 'com.example'\nversion = '0.0.1-SNAPSHOT'\n\nrepositories {\n    mavenCentral()\n}\n\ndependencies {\n    implementation 'org.springframework.boot:spring-boot-starter-web'\n    testImplementation 'org.springframework.boot:spring-boot-starter-test'\n}"
}

EXPANDED_V41_45["maven_groovy"] = {
    "XML": "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">\n    <modelVersion>4.0.0</modelVersion>\n    <groupId>com.example</groupId>\n    <artifactId>my-app</artifactId>\n    <version>1.0.0</version>\n    <dependencies>\n        <dependency>\n            <groupId>junit</groupId>\n            <artifactId>junit</artifactId>\n            <version>4.13.2</version>\n            <scope>test</scope>\n        </dependency>\n    </dependencies>\n</project>"
}

# WAVE 43: Package Managers
EXPANDED_V41_45["npm_package_json"] = {
    "JSON": "{\n  \"name\": \"my-app\",\n  \"version\": \"1.0.0\",\n  \"scripts\": {\n    \"start\": \"node index.js\",\n    \"test\": \"jest\"\n  },\n  \"dependencies\": {\n    \"express\": \"^4.18.2\"\n  },\n  \"devDependencies\": {\n    \"jest\": \"^29.0.0\"\n  }\n}"
}

EXPANDED_V41_45["cargo_toml"] = {
    "TOML": "[package]\nname = \"my_app\"\nversion = \"0.1.0\"\nedition = \"2021\"\nauthors = [\"Alice <alice@example.com>\"]\n\n[dependencies]\nserde = { version = \"1.0\", features = [\"derive\"] }\ntokio = { version = \"1.28\", features = [\"full\"] }\n\n[dev-dependencies]\nassert_cmd = \"2.0\""
}

EXPANDED_V41_45["requirements_txt"] = {
    "Text": "Flask==2.3.2\nrequests>=2.28.0\nSQLAlchemy~=2.0.0\npytest==7.3.1  # For testing"
}

EXPANDED_V41_45["go_mod"] = {
    "Go": "module github.com/user/myapp\n\ngo 1.20\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n\tgorm.io/gorm v1.25.0\n)\n\nreplace github.com/user/fork => ../fork"
}

EXPANDED_V41_45["composer_json"] = {
    "JSON": "{\n    \"name\": \"vendor/package\",\n    \"require\": {\n        \"php\": \"^8.1\",\n        \"guzzlehttp/guzzle\": \"^7.5\"\n    },\n    \"require-dev\": {\n        \"phpunit/phpunit\": \"^10.0\"\n    },\n    \"autoload\": {\n        \"psr-4\": {\n            \"App\\\\\": \"src/\"\n        }\n    }\n}"
}

# WAVE 44: Testing Frameworks
EXPANDED_V41_45["unit_testing_frameworks"] = {
    "Python": "import unittest\n\nclass TestMath(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\nif __name__ == '__main__':\n    unittest.main()",
    "JavaScript": "// Jest\ntest('adds 2 + 3 to equal 5', () => {\n  expect(add(2, 3)).toBe(5);\n});",
    "Java": "import org.junit.jupiter.api.Test;\nimport static org.junit.jupiter.api.Assertions.assertEquals;\n\nclass MathTest {\n    @Test\n    void testAdd() {\n        assertEquals(5, add(2, 3));\n    }\n}",
    "Go": "import \"testing\"\n\nfunc TestAdd(t *testing.T) {\n    if add(2, 3) != 5 {\n        t.Errorf(\"Expected 5, got %d\", add(2, 3))\n    }\n}",
    "Rust": "#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn test_add() {\n        assert_eq!(add(2, 3), 5);\n    }\n}",
    "Ruby": "require 'minitest/autorun'\n\nclass TestMath < Minitest::Test\n  def test_add\n    assert_equal 5, add(2, 3)\n  end\nend",
    "C#": "using Xunit;\n\npublic class MathTests {\n    [Fact]\n    public void TestAdd() {\n        Assert.Equal(5, Add(2, 3));\n    }\n}",
    "C++": "// Google Test\n#include <gtest/gtest.h>\n\nTEST(MathTest, AddsTwoNumbers) {\n  EXPECT_EQ(add(2, 3), 5);\n}\n\nint main(int argc, char **argv) {\n  ::testing::InitGoogleTest(&argc, argv);\n  return RUN_ALL_TESTS();\n}"
}

EXPANDED_V41_45["mocking_stubbing"] = {
    "Python": "from unittest.mock import MagicMock\nservice = MagicMock()\nservice.get_data.return_value = {\"status\": \"ok\"}\n# Calls to service.get_data() return the dict immediately",
    "JavaScript": "// Jest\nconst mockFn = jest.fn();\nmockFn.mockReturnValue('default');\n// Or mock entire modules: jest.mock('axios');",
    "Java": "// Mockito\nimport static org.mockito.Mockito.*;\nList mockedList = mock(List.class);\nwhen(mockedList.get(0)).thenReturn(\"first\");\nSystem.out.println(mockedList.get(0)); // \"first\"",
    "C#": "// Moq\nusing Moq;\nvar mock = new Mock<IService>();\nmock.Setup(s => s.GetData()).Returns(new Data());",
    "Go": "// gomock\n// ctrl := gomock.NewController(t)\n// defer ctrl.Finish()\n// m := NewMockMyInterface(ctrl)\n// m.EXPECT().MyMethod(1).Return(true)"
}

# WAVE 45: Concurrency Primitives & Paradigms
EXPANDED_V41_45["promises_futures_deferred"] = {
    "JavaScript": "const p = new Promise((resolve, reject) => {\n  setTimeout(() => resolve(\"Done\"), 1000);\n});\np.then(res => console.log(res)).catch(err => console.error(err));",
    "Python": "# asyncio.Future\nimport asyncio\nasync def main():\n    loop = asyncio.get_running_loop()\n    fut = loop.create_future()\n    loop.call_later(1, fut.set_result, \"Done\")\n    print(await fut)\nasyncio.run(main())",
    "Java": "CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {\n    try { Thread.sleep(1000); } catch(Exception e) {}\n    return \"Done\";\n});\nfuture.thenAccept(System.out::println).join();",
    "C++": "#include <future>\n#include <thread>\nstd::promise<std::string> prom;\nstd::future<std::string> fut = prom.get_future();\nstd::thread t([](std::promise<std::string> p) { \n    std::this_thread::sleep_for(std::chrono::seconds(1));\n    p.set_value(\"Done\"); \n}, std::move(prom));\nstd::cout << fut.get();\nt.join();",
    "Rust": "// Tokio / Futures\n// use futures::channel::oneshot;\n// let (tx, rx) = oneshot::channel();\n// tokio::spawn(async move { tx.send(\"Done\").unwrap(); });\n// println!(\"{}\", rx.await.unwrap());",
    "C#": "TaskCompletionSource<string> tcs = new TaskCompletionSource<string>();\nTask.Run(async () => {\n    await Task.Delay(1000);\n    tcs.SetResult(\"Done\");\n});\nConsole.WriteLine(await tcs.Task);"
}
