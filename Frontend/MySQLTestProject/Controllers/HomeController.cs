using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using MySQLTestProject.Data;
using Newtonsoft.Json;
using System.Net.Http;
using System.Text;

namespace MySQLTestProject.Controllers
{
    public class HomeController : Controller
    {
        private readonly AppDbContext _context;
        private readonly IHttpClientFactory _clientFactory;
        private readonly IConfiguration _config;

        public HomeController(
            AppDbContext context,
            IHttpClientFactory clientFactory,
            IConfiguration config)
        {
            _context = context;
            _clientFactory = clientFactory;
            _config = config;
        }

        public IActionResult Index()
        {
            return View();
        }

        [HttpPost]
        public async Task<IActionResult> GenerateQuery(string userInput)
        {
            string sqlQuery = "Error: Could not generate SQL";
            List<Employee> result = new();
            string modelError = null;
            string executionError = null;

            try
            {
                var apiUrl = _config["NlpApi:BaseUrl"] + "/generate-sql";
                var client = _clientFactory.CreateClient();

                var requestData = new { query = userInput };
                var jsonContent = new StringContent(
                    JsonConvert.SerializeObject(requestData),
                    Encoding.UTF8,
                    "application/json"
                );

                var response = await client.PostAsync(apiUrl, jsonContent);

                if (response.IsSuccessStatusCode)
                {
                    var jsonResponse = await response.Content.ReadAsStringAsync();
                    dynamic apiData = JsonConvert.DeserializeObject(jsonResponse);

                    if (apiData.error != null)
                    {
                        modelError = apiData.error.ToString();
                    }
                    else
                    {
                        sqlQuery = apiData.sql?.ToString()?.Trim() ?? sqlQuery; 
                    }
                }
                else
                {
                    var errorContent = await response.Content.ReadAsStringAsync();
                    modelError = $"API Error ({response.StatusCode}): {errorContent}";
                }

                if (string.IsNullOrEmpty(modelError) &&
                    sqlQuery.StartsWith("SELECT", StringComparison.OrdinalIgnoreCase))
                {
                    try
                    {
                        result = await _context.Employees
                            .FromSqlRaw(sqlQuery)
                            .AsNoTracking()
                            .ToListAsync();

                        Console.WriteLine($"[DEBUG] Query executed: {sqlQuery}");
                        Console.WriteLine($"[DEBUG] Rows returned: {result.Count}");
                    }
                    catch (Exception ex)
                    {
                        executionError = $"SQL Execution failed: {ex.Message}";
                        Console.WriteLine($"[ERROR] SQL Execution failed: {sqlQuery}");
                        Console.WriteLine($"[ERROR] Exception: {ex}");
                    }
                }
            }
            catch (Exception ex)
            {
                modelError = $"System error: {ex.Message}";
                Console.WriteLine($"[ERROR] System exception: {ex}");
            }

            ViewBag.GeneratedQuery = sqlQuery;
            ViewBag.Result = result ?? new List<Employee>();
            ViewBag.ModelError = modelError;
            ViewBag.ExecutionError = executionError;

            return View("Index");
        }
    }
}
